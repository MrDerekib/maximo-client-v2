import tests
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtTest import QTest,QSignalSpy
from ui_activity_icon import RefreshIcon
from tests import test_filters as fixtures


class ActivityIconTests(TestCase):
    def test_animation_advances_stops_and_keeps_color_change_running(self):
        app=QApplication.instance() or QApplication([])
        button=QPushButton();button.show()
        icon=RefreshIcon(button,Path(__file__).resolve().parents[1]/'ui_assets'/'refresh-white.svg','#ffffff')
        try:
            self.assertFalse(icon.timer.isActive())
            ticks=QSignalSpy(icon.timer.timeout)
            icon.set_running(True)
            self.assertTrue(ticks.wait(2000))
            self.assertTrue(icon.timer.isActive());self.assertGreater(icon.angle,0)
            icon.set_color('#202020');self.assertTrue(icon.running)
            icon.set_running(False)
            self.assertFalse(icon.timer.isActive());self.assertEqual(icon.angle,0)
        finally:button.close();button.deleteLater();app.processEvents()

    def test_update_success_failure_and_start_failure_release_animation(self):
        fixture=fixtures.FilterTests('runTest');fixture.setUp()
        try:
            with fixture.qt_window() as (window,qt):
                with patch.object(window,'_credentials_ready',return_value=True),patch.object(window,'_start_task') as task,patch.object(qt.QMessageBox,'critical'),patch.object(window,'start_background_reconcile'):
                    window.update_now();self.assertTrue(window.update_icon.running)
                    task.call_args.args[1]((0,0));self.assertFalse(window.update_icon.running)
                    window.update_now();self.assertTrue(window.update_icon.running)
                    task.call_args.args[2]('fallo ficticio');self.assertFalse(window.update_icon.running)
                    task.side_effect=RuntimeError('No se pudo iniciar')
                    window.update_now();self.assertFalse(window.update_icon.running)
                    self.assertFalse(window._list_update_pending);self.assertFalse(window.update_lock.locked())
        finally:fixture.doCleanups()

    def test_sidebar_excel_uses_existing_priority_importer_and_can_cancel(self):
        fixture=fixtures.FilterTests('runTest');fixture.setUp()
        try:
            with fixture.qt_window() as (window,qt):
                self.assertTrue(window.sidebar.isAncestorOf(window.load_excel_button))
                with patch.object(qt.QFileDialog,'getOpenFileNames',return_value=([],'')) as picker,patch.object(qt,'read_priority_files') as read:
                    window.load_excel_button.click();picker.assert_called_once();read.assert_not_called()
        finally:fixture.doCleanups()
