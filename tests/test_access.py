import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

from tests.test_support import temporary_directory

import maximo_client as client
import updater


class AccessTests(unittest.TestCase):
    def test_pending_repair_lookup_is_clicked_by_webdriver(self):
        option_id = "lookup_page3_tdrow_[C:1]_ttxt-lb[R:0]"
        option = Mock()
        option.is_displayed.return_value = True
        driver = Mock()
        driver.execute_script.side_effect = [option_id, None]
        driver.find_elements.return_value = [option]

        self.assertTrue(client._click_pending_repair_lookup(driver))

        driver.find_elements.assert_called_once_with(client.By.ID, option_id)
        option.click.assert_called_once_with()
        self.assertIn("maximoNativeLookupClick", driver.execute_script.call_args.args[0])

    def test_pending_lookup_click_rejects_unexpected_ids(self):
        driver = Mock()
        driver.execute_script.return_value = "mx45-tb"

        self.assertFalse(client._click_pending_repair_lookup(driver))

        driver.find_elements.assert_not_called()
        self.assertIn("delete document.documentElement.dataset.maximoNativeLookupClick",
                      driver.execute_script.call_args.args[0])

    def test_close_after_direct_print_requires_visible_default_printer(self):
        self.assertTrue(client._should_close_after_direct_print(True, False, "Office Printer"))
        self.assertFalse(client._should_close_after_direct_print(True, False, ""))
        self.assertFalse(client._should_close_after_direct_print(True, True, "Office Printer"))
        self.assertFalse(client._should_close_after_direct_print(False, False, "Office Printer"))

    def test_repair_extension_print_mode_applies_only_to_visible_edge(self):
        with temporary_directory() as directory:
            root = Path(directory)
            extension = root / "browser_extension"
            extension.mkdir()
            (extension / "manifest.json").write_text("{}", encoding="utf-8")
            cfg = SimpleNamespace(download_dir=directory, repair_extension_enabled=True,
                                  repair_print_mode="direct")
            with patch.object(client, "PROGRAM_DIR", root), \
                 patch.object(client, "load_config", return_value=cfg), \
                 patch.object(client, "default_printer_name", return_value="Printer") as default_printer, \
                 patch.object(client.webdriver, "Edge", return_value=Mock()) as launch:
                client.setup_driver(headless=False, profile_dir=str(root / "visible"))
                arguments = launch.call_args.kwargs["options"].arguments
                self.assertIn(f"--load-extension={extension}", arguments)
                self.assertIn("--kiosk-printing", arguments)

                cfg.repair_print_mode = "dialog"
                client.setup_driver(headless=False, profile_dir=str(root / "dialog"))
                arguments = launch.call_args.kwargs["options"].arguments
                self.assertIn(f"--load-extension={extension}", arguments)
                self.assertNotIn("--kiosk-printing", arguments)

                cfg.repair_print_mode = "direct"
                default_printer.return_value = ""
                client.setup_driver(headless=False, profile_dir=str(root / "no-printer"))
                arguments = launch.call_args.kwargs["options"].arguments
                self.assertNotIn("--kiosk-printing", arguments)

                cfg.repair_print_mode = "direct"
                client.setup_driver(headless=True, profile_dir=str(root / "background"))
                arguments = launch.call_args.kwargs["options"].arguments
                self.assertFalse(any(argument.startswith("--load-extension=") for argument in arguments))
                self.assertNotIn("--kiosk-printing", arguments)

    def test_desktop_report_forces_extension_and_starts_only_for_matching_ot(self):
        with temporary_directory() as directory:
            root = Path(directory)
            extension = root / "browser_extension"
            extension.mkdir()
            (extension / "manifest.json").write_text("{}", encoding="utf-8")
            cfg = SimpleNamespace(download_dir=directory, repair_extension_enabled=False,
                                  repair_print_mode="dialog")
            with patch.object(client, "PROGRAM_DIR", root), \
                 patch.object(client, "load_config", return_value=cfg), \
                 patch.object(client.webdriver, "Edge", return_value=Mock()) as launch:
                client.setup_driver(headless=False, profile_dir=str(root / "report"),
                                    force_repair_extension=True)
                self.assertIn(f"--load-extension={extension}",
                              launch.call_args.kwargs["options"].arguments)

        driver = Mock()
        number = Mock()
        number.get_attribute.side_effect = ["other", "4228010"]
        status = Mock()
        status.get_attribute.return_value = "ISSUE"
        button = Mock()
        button.is_displayed.return_value = True
        button.is_enabled.return_value = True
        driver.find_element.side_effect = lambda _, id: (
            number if id == "mx45-tb" else status if id == "mx73-tb" else button
        )

        def wait(browser, condition, description, timeout):
            if "carga de la OT" in description:
                self.assertFalse(condition(browser))
                return condition(browser)
            return condition(browser)

        with patch.object(client, "wait_for", side_effect=wait):
            client.start_repair_report(driver, "4228010", "pdf")
        driver.execute_script.assert_called_once_with(
            "arguments[0].dataset.maximoReportAction = arguments[1]; "
            "arguments[0].dataset.maximoCloseReportTabs = arguments[2] ? 'true' : 'false'; "
            "arguments[0].click();",
            button, "pdf", False)

    def test_desktop_direct_print_passes_close_tabs_policy_to_extension(self):
        driver = Mock()
        number = Mock()
        number.get_attribute.return_value = "4228010"
        status = Mock()
        status.get_attribute.return_value = "ISSUE"
        button = Mock()
        button.is_displayed.return_value = True
        button.is_enabled.return_value = True
        driver.find_element.side_effect = lambda _, id: (
            number if id == "mx45-tb" else status if id == "mx73-tb" else button
        )
        with patch.object(client, "wait_for", side_effect=lambda browser, condition, *_args, **_kwargs: condition(browser)):
            client.start_repair_report(driver, "4228010", "print", close_after_direct_print=True)
        self.assertTrue(driver.execute_script.call_args.args[3])

    def test_desktop_report_stops_before_extension_for_ineligible_status(self):
        driver = Mock()
        number = Mock()
        number.get_attribute.return_value = "4228010"
        status = Mock()
        status.get_attribute.return_value = "APPR"
        driver.find_element.side_effect = lambda _, id: number if id == "mx45-tb" else status
        with patch.object(client, "wait_for", side_effect=lambda browser, condition, *_args, **_kwargs: condition(browser)):
            with self.assertRaisesRegex(RuntimeError, "no admite parte"):
                client.start_repair_report(driver, "4228010", "print")
        driver.execute_script.assert_not_called()

    def test_visible_ot_profiles_start_with_monochrome_printing_without_headers(self):
        with temporary_directory() as directory, \
             patch.object(client, "load_config", return_value=SimpleNamespace(download_dir=directory)), \
             patch.object(client.webdriver, "Edge", return_value=Mock()) as launch:
            client.setup_driver(headless=False, profile_dir=str(Path(directory) / "visible"))
            visible_prefs = launch.call_args.kwargs["options"].experimental_options["prefs"]
            app_state = json.loads(visible_prefs["printing.print_preview_sticky_settings"]["appState"])
            self.assertIs(app_state["isColorEnabled"], False)
            self.assertIs(app_state["isHeaderFooterEnabled"], False)
            self.assertEqual(app_state["recentDestinations"], [])

            client.setup_driver(headless=True, profile_dir=str(Path(directory) / "background"))
            background_prefs = launch.call_args.kwargs["options"].experimental_options["prefs"]
            self.assertNotIn("printing.print_preview_sticky_settings", background_prefs)

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

    def test_complete_xls_is_accepted_beside_stale_partial(self):
        with temporary_directory() as directory:
            folder = Path(directory)
            partial = folder / "stale.xls.crdownload"
            result = folder / "new.xls"

            def wait(driver, condition, description, *args):
                if description == "botón de descarga":
                    return Mock()
                partial.write_bytes(b"unfinished")
                result.write_bytes(b"complete")
                self.assertFalse(condition(driver))
                return condition(driver)

            with patch.object(client, "wait_for", side_effect=wait):
                self.assertEqual(client.download_file(Mock(), directory), str(result))

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
        workorder_field = driver.find_element.return_value
        workorder_field.get_attribute.return_value = "99"
        self.assertFalse(loaded(driver))
        workorder_field.get_attribute.return_value = "100"
        self.assertTrue(loaded(driver))
        driver.find_element.assert_called_with(client.By.ID, "mx45-tb")

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

    def test_export_retries_once_with_clean_edge_and_updates_database_once(self):
        with temporary_directory() as directory:
            drivers = [Mock(), Mock()]
            exported = Path(directory) / "export.xls"
            with patch.object(updater, "load_config", return_value=SimpleNamespace(download_dir=directory)), \
                 patch.object(client, "EDGE_PROFILE_DIR", Path(directory) / "edge-profiles"), \
                 patch.object(updater, "setup_driver", side_effect=drivers) as setup, \
                 patch.object(updater, "login"), patch.object(updater, "open_workorders_app"), \
                 patch.object(updater, "download_file", side_effect=[
                     client.ExportDownloadTimeout("no se inició"), "new.xls"
                 ]) as download, \
                 patch.object(updater, "move_downloaded_file", return_value=str(exported)), \
                 patch.object(updater, "process_html_table", return_value=Mock()), \
                 patch.object(updater, "update_database_from_df", return_value=(1, 2)) as update_db, \
                 patch.object(updater, "cleanup_exports"):
                self.assertEqual(updater.run_update(), (1, 2))
            self.assertEqual(setup.call_count, 2)
            self.assertEqual(download.call_count, 2)
            self.assertNotEqual(
                setup.call_args_list[0].kwargs["profile_dir"],
                setup.call_args_list[1].kwargs["profile_dir"],
            )
            for call in setup.call_args_list:
                self.assertFalse(Path(call.kwargs["profile_dir"]).exists())
                self.assertFalse(Path(call.kwargs["download_dir"]).exists())
            for driver in drivers:
                driver.quit.assert_called_once()
            update_db.assert_called_once()

    def test_two_export_timeouts_leave_database_unchanged(self):
        with temporary_directory() as directory:
            drivers = [Mock(), Mock()]
            with patch.object(updater, "load_config", return_value=SimpleNamespace(download_dir=directory)), \
                 patch.object(client, "EDGE_PROFILE_DIR", Path(directory) / "edge-profiles"), \
                 patch.object(updater, "setup_driver", side_effect=drivers), \
                 patch.object(updater, "login"), patch.object(updater, "open_workorders_app"), \
                 patch.object(updater, "download_file", side_effect=client.ExportDownloadTimeout("sin XLS")) as download, \
                 patch.object(updater, "update_database_from_df") as update_db:
                with self.assertRaises(client.ExportDownloadTimeout):
                    updater.run_update()
            self.assertEqual(download.call_count, 2)
            update_db.assert_not_called()
            for driver in drivers:
                driver.quit.assert_called_once()

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
