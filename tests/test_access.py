import threading
import logging
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

from tests.test_support import temporary_directory

import maximo_client as client
import updater
with patch("logging.handlers.RotatingFileHandler", return_value=logging.NullHandler()), patch("logging.basicConfig"):
    import gui_main


class AccessTests(unittest.TestCase):
    def _check_releases(self, results, notify=True):
        app = SimpleNamespace(cfg=SimpleNamespace(), after=Mock(), _refresh_update_block=Mock())
        def thread(**kwargs):
            return SimpleNamespace(start=kwargs["target"])
        with patch.object(gui_main.threading, "Thread", side_effect=thread), \
             patch.object(gui_main, "fetch_latest_release", side_effect=results), \
             patch.object(gui_main, "save_config"), patch.object(gui_main.time, "sleep"), \
             self.assertLogs(level="INFO") as logs:
            gui_main.MaximoApp.check_updates(app, notify)
        return [line for line in logs.output if line.startswith("WARNING")]

    def test_release_retry_success_does_not_warn_of_final_failure(self):
        release = SimpleNamespace(tag="v0.9.2", html_url="https://example.invalid", checked_at="today")
        self.assertEqual(self._check_releases([OSError("connection closed"), release]), [])

    def test_release_exhaustion_warns_once_with_actual_attempt_count(self):
        for notify, count in ((True, 3), (False, 1)):
            warnings = self._check_releases([OSError("connection closed")] * count, notify)
            self.assertEqual(len(warnings), 1)
            self.assertIn(f"tras {count} intento(s)", warnings[0])

    def test_running_update_blocks_another_worker(self):
        app = SimpleNamespace(
            _ensure_credentials=Mock(return_value=True),
            update_lock=threading.Lock(),
        )
        app.update_lock.acquire()
        with patch.object(gui_main.threading, "Thread") as thread:
            gui_main.MaximoApp.update_now_threaded(app, show_popup=False)
            thread.assert_not_called()
        app.update_lock.release()

    def test_worker_releases_lock_after_failure(self):
        app = SimpleNamespace(update_lock=threading.Lock(), after=Mock())
        app.update_lock.acquire()
        with patch.object(gui_main, "run_update", side_effect=RuntimeError("failed")):
            gui_main.MaximoApp._update_now_worker(app, show_popup=False)
        self.assertFalse(app.update_lock.locked())

    def test_worker_releases_lock_after_success(self):
        app = SimpleNamespace(update_lock=threading.Lock(), after=Mock())
        app.update_lock.acquire()
        with patch.object(gui_main, "run_update", return_value=(2, 3)):
            gui_main.MaximoApp._update_now_worker(app, show_popup=False)
        self.assertFalse(app.update_lock.locked())

    def test_wait_retries_stale_elements(self):
        condition = Mock(side_effect=[StaleElementReferenceException(), "ready"])
        self.assertEqual(client.wait_for(Mock(), condition, "pantalla", timeout=1), "ready")

    def test_wait_reports_failed_stage(self):
        with self.assertRaisesRegex(TimeoutException, "pantalla de prueba"):
            client.wait_for(Mock(), lambda _: False, "pantalla de prueba", timeout=0)

    def test_download_ignores_old_and_partial_files(self):
        with temporary_directory() as directory:
            folder = Path(directory)
            old = folder / "old.xls"
            old.write_bytes(b"old")
            partial = folder / "new.xls.crdownload"
            result = folder / "new.xls"

            def wait(driver, condition, description, *args):
                if description == "botón de descarga":
                    return Mock()
                self.assertFalse(condition(driver))  # Solo hay un XLS antiguo.
                partial.write_bytes(b"partial")
                self.assertFalse(condition(driver))
                partial.rename(result)
                self.assertFalse(condition(driver))  # Primera observación.
                result.write_bytes(b"complete download")
                self.assertFalse(condition(driver))  # Sigue cambiando.
                return condition(driver)

            with patch.object(client, "wait_for", side_effect=wait):
                self.assertEqual(client.download_file(Mock(), directory), str(result))
            self.assertEqual(old.read_bytes(), b"old")

    def test_empty_download_times_out(self):
        with temporary_directory() as directory:
            driver = Mock()
            driver.find_element.return_value.is_displayed.return_value = True
            driver.find_element.return_value.is_enabled.return_value = True
            with self.assertRaisesRegex(TimeoutException, "descarga XLS"):
                client.download_file(driver, directory, timeout=0)

    def test_archive_preserves_existing_exports(self):
        with temporary_directory() as directory:
            folder = Path(directory)
            exports = folder / "exports"
            exports.mkdir()
            existing = exports / "export.xls"
            existing.write_bytes(b"previous")
            source = folder / "export.xls"
            source.write_bytes(b"new")
            with patch.object(client, "load_config", return_value=SimpleNamespace(dest_folder=str(exports))):
                archived = Path(client.move_downloaded_file(source))
            self.assertEqual(existing.read_bytes(), b"previous")
            self.assertEqual(archived.read_bytes(), b"new")
            self.assertFalse(source.exists())

    def test_login_waits_for_authenticated_screen(self):
        driver = Mock()
        driver.find_elements.return_value = []

        def wait(browser, condition, description, *args):
            if description != "inicio de sesión":
                return Mock()
            with patch.object(client.EC, "invisibility_of_element_located") as invisible:
                invisible.return_value.return_value = False
                self.assertFalse(condition(browser))
                invisible.return_value.return_value = True
                browser.execute_script.return_value = False
                self.assertFalse(condition(browser))
                browser.execute_script.return_value = True
                self.assertTrue(condition(browser))

        with patch.object(client, "load_config", return_value=SimpleNamespace(maximo_url="https://example.invalid")), \
             patch.object(client, "get_credentials", return_value=("user", "password")), \
             patch.object(client, "wait_for", side_effect=wait):
            client.login(driver)

    def test_login_rejection_is_not_success(self):
        driver = Mock()
        error = Mock()
        error.text = "BMXAA7901E"
        driver.find_elements.return_value = [error]

        def wait(browser, condition, description, *args):
            return condition(browser) if description == "inicio de sesión" else Mock()

        with patch.object(client, "load_config", return_value=SimpleNamespace(maximo_url="https://example.invalid")), \
             patch.object(client, "get_credentials", return_value=("user", "password")), \
             patch.object(client, "wait_for", side_effect=wait):
            with self.assertRaisesRegex(RuntimeError, "Login rechazado"):
                client.login(driver)

    def test_login_uses_explicit_credentials_without_reading_saved_values(self):
        driver = Mock()
        driver.find_elements.return_value = []

        def wait(browser, condition, description, *args):
            if description == "inicio de sesión":
                with patch.object(client.EC, "invisibility_of_element_located") as invisible:
                    invisible.return_value.return_value = True
                    browser.execute_script.return_value = True
                    return condition(browser)
            return Mock()

        with patch.object(client, "load_config", return_value=SimpleNamespace(maximo_url="https://example.invalid")), \
             patch.object(client, "get_credentials") as saved, \
             patch.object(client, "wait_for", side_effect=wait):
            client.login(driver, username="nuevo-usuario", password="clave temporal")
        saved.assert_not_called()
        password_field = driver.find_element.call_args_list[-1].args[1]
        self.assertEqual(password_field, "password")

    def test_verify_credentials_closes_driver_and_profile(self):
        driver = Mock()
        with patch.object(client, "create_edge_profile", return_value="C:/test-profile"), \
             patch.object(client, "setup_driver", return_value=driver) as setup, \
             patch.object(client, "login") as login, \
             patch.object(client.shutil, "rmtree") as cleanup:
            client.verify_credentials(" usuario ", "clave temporal")
        setup.assert_called_once_with(headless=True, profile_dir="C:/test-profile")
        login.assert_called_once_with(driver, headless=True, username="usuario", password="clave temporal")
        driver.quit.assert_called_once()
        cleanup.assert_called_once_with(Path("C:/test-profile"))

    def test_read_workorder_status_uses_mx73_field(self):
        search = Mock()
        status = Mock()
        status.get_attribute.return_value = " DAR\u00a0SALIDA "
        driver = Mock()
        with patch.object(client, "wait_for", side_effect=[search, True, status]) as wait:
            self.assertEqual(client.read_workorder_status(driver, "100"), "DAR SALIDA")
        self.assertEqual(wait.call_args_list[1].args[2], "carga de la OT 100 para conciliación")
        self.assertEqual(wait.call_args_list[2].args[2], "estado real de la OT 100")
        loaded = wait.call_args_list[1].args[1]
        driver.execute_script.return_value = False
        self.assertFalse(loaded(driver))
        driver.execute_script.return_value = True
        self.assertTrue(loaded(driver))
        self.assertIn("element.id !== 'quicksearch'", driver.execute_script.call_args.args[0])

    def test_reconciliation_reuses_one_headless_session(self):
        driver = Mock()
        with patch.object(updater, "inactive_tracking_candidates", return_value=[("1", "EN TALLER"), ("2", "APPR")]), \
             patch.object(updater, "create_edge_profile", return_value="C:/reconcile-profile"), \
             patch.object(updater, "setup_driver", return_value=driver) as setup, \
             patch.object(updater, "login"), patch.object(updater, "open_workorders_app"), \
            patch.object(updater, "read_workorder_status", side_effect=["DAR SALIDA", "APPR"]), \
             patch.object(updater, "apply_reconciled_status", return_value=True) as apply, \
             patch.object(updater, "cleanup_edge_profile") as cleanup:
            self.assertEqual(updater.reconcile_inactive_tracking(), 1)
        setup.assert_called_once_with(headless=True, profile_dir="C:/reconcile-profile")
        self.assertEqual(apply.call_count, 2)
        driver.quit.assert_called_once()
        cleanup.assert_called_once_with("C:/reconcile-profile")

    def test_failed_download_never_updates_database_and_cleans_up(self):
        with temporary_directory() as directory:
            driver = Mock()
            with patch.object(updater, "load_config", return_value=SimpleNamespace(download_dir=directory)), \
                 patch.object(client, "EDGE_PROFILE_DIR", Path(directory) / "edge-profiles"), \
                 patch.object(updater, "setup_driver", return_value=driver) as setup, \
                 patch.object(updater, "login"), patch.object(updater, "open_workorders_app"), \
                 patch.object(updater, "download_file", side_effect=TimeoutException("failed")), \
                 patch.object(updater, "update_database_from_df") as update_db:
                with self.assertRaises(TimeoutException):
                    updater.run_update()
                update_db.assert_not_called()
                driver.quit.assert_called_once()
                self.assertFalse(Path(setup.call_args.kwargs["profile_dir"]).exists())
                self.assertFalse(Path(setup.call_args.kwargs["download_dir"]).exists())

    def test_visible_ots_keep_independent_sessions(self):
        drivers = [Mock(), Mock()]
        sessions = []
        try:
            with temporary_directory() as directory, \
                 patch.object(client, "EDGE_PROFILE_DIR", Path(directory) / "edge-profiles"), \
                 patch.object(client, "setup_driver", side_effect=drivers), \
                 patch.object(client, "login"), patch.object(client, "open_workorders_app"), \
                 patch.object(client, "wait_for", return_value=Mock()):
                sessions.append(client.open_ot("100"))
                sessions.append(client.open_ot("200"))
            self.assertIs(sessions[0][0], drivers[0])
            self.assertIs(sessions[1][0], drivers[1])
            self.assertNotEqual(sessions[0][1], sessions[1][1])
            for driver in drivers:
                driver.quit.assert_not_called()
        finally:
            for _, profile in sessions:
                shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
