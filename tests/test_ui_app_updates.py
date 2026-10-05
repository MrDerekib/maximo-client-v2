"""La UI solo debe instalar tras aceptar el cierre y limpiar sus tareas."""
import logging
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from update_checker import LatestRelease
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
with patch("logging.handlers.RotatingFileHandler", return_value=logging.NullHandler()), patch("logging.basicConfig"):
    from ui_qt import QApplication, MaximoDesktopWindow, QMessageBox, QProgressDialog


class AppUpdateFlowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_completing_download_does_not_emit_cancel(self):
        cancel = threading.Event()
        dialog = QProgressDialog()
        dialog.canceled.connect(cancel.set)
        window = SimpleNamespace(app_download_dialog=dialog)
        MaximoDesktopWindow._close_app_download_dialog(window)
        self.assertFalse(cancel.is_set())
        self.assertIsNone(window.app_download_dialog)

    def test_startup_prompts_once_for_installable_release(self):
        release = LatestRelease("v9.1.0", "https://example.test/release", "hoy", "https://example.test/app.zip", "sha256:abc")
        window = SimpleNamespace(
            _closing=False, _app_update_checking=False, _app_update_downloading=False,
            _prompted_release_tags=set(), _latest_release=None,
            cfg=SimpleNamespace(), install_update_button=Mock(),
            _refresh_app_update_block=Mock(), install_latest_release=Mock(),
            _fetch_latest_release_with_retry=Mock(return_value=release),
            _start_task=lambda work, done, failed: done(work()),
        )
        window.install_update_button.isEnabled.return_value = True
        with patch("ui_qt.save_config"), patch("ui_qt.QMessageBox.question", return_value=QMessageBox.Yes) as question:
            MaximoDesktopWindow.check_app_updates(window, automatic=True)
            MaximoDesktopWindow.check_app_updates(window, automatic=True)
        question.assert_called_once()
        window.install_latest_release.assert_called_once()

    def test_development_build_cannot_install_published_release(self):
        release = LatestRelease("v9.1.0", "https://example.test/release", "hoy", "https://example.test/app.zip", "sha256:abc")
        window = SimpleNamespace(
            cfg=SimpleNamespace(latest_release_tag=release.tag, latest_release_url=release.html_url, latest_release_checked_at="hoy"),
            _latest_release=release, _closing=False, _app_update_checking=False, _app_update_downloading=False,
            app_version_label=Mock(), app_latest_label=Mock(), app_last_check_label=Mock(),
            open_release_button=Mock(), check_app_updates_button=Mock(),
            install_update_button=Mock(), app_update_status_label=Mock(),
        )
        with patch("ui_qt.DEVELOPMENT_MODE", True), patch("ui_qt.distributed_executable", return_value=Path("C:/App/MaximoDesktop.exe")):
            MaximoDesktopWindow._refresh_app_update_block(window)
        window.install_update_button.setEnabled.assert_called_once_with(False)
        self.assertIn("desarrollo", window.app_update_status_label.setText.call_args.args[0])

    def test_rejecting_close_keeps_installer_unarmed(self):
        window = SimpleNamespace(_closing=False, close=Mock(), _refresh_app_update_block=Mock())
        with patch("ui_qt.distributed_executable", return_value=Path("C:/App/MaximoDesktop.exe")):
            MaximoDesktopWindow._begin_update_close(window, Path("C:/Cache/files"))
        window.close.assert_called_once()
        self.assertIsNone(window._pending_update)

    def test_installer_starts_after_orderly_close(self):
        events = []
        executable = Path("C:/App/MaximoDesktop.exe")
        source = Path("C:/Cache/files")
        window = SimpleNamespace(
            close_progress=SimpleNamespace(emit=lambda message: events.append("progress")),
            close_dialog=SimpleNamespace(close=lambda: events.append("dialog_closed")),
            _pending_update=(executable, source), _close_finalized=False,
            close=lambda: events.append("window_closed"),
        )
        with patch("ui_qt.start_update", side_effect=lambda *args: events.append("installer_started")) as installer:
            MaximoDesktopWindow._finish_close(window)
        installer.assert_called_once_with(executable, source)
        self.assertEqual(events, ["progress", "dialog_closed", "installer_started", "window_closed"])
        self.assertTrue(window._close_finalized)

    def test_installer_failure_keeps_window_open(self):
        window = SimpleNamespace(
            close_progress=SimpleNamespace(emit=Mock()), close_dialog=SimpleNamespace(close=Mock()),
            _pending_update=(Path("C:/App/MaximoDesktop.exe"), Path("C:/Cache/files")),
            _closing=True, _close_finalized=False, enrichment_cancel_event=SimpleNamespace(clear=Mock()),
            schedule_auto_update=Mock(), _refresh_app_update_block=Mock(), close=Mock(),
        )
        with self.assertLogs(level="ERROR"), patch("ui_qt.start_update", side_effect=OSError("fallo")), patch("ui_qt.QMessageBox.critical") as error:
            MaximoDesktopWindow._finish_close(window)
        window.close.assert_not_called()
        self.assertFalse(window._closing)
        self.assertFalse(window._close_finalized)
        self.assertIsNone(window._pending_update)
        error.assert_called_once()
