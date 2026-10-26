"""The UI keeps opening and starting as separate, opt-in actions."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from config import AppConfig
from tests.test_ui_app_updates import QApplication, MaximoDesktopWindow
from PySide6.QtWidgets import QMainWindow


def window(enabled=True):
    return SimpleNamespace(
        _closing=False, cfg=AppConfig(workorder_start_enabled=enabled),
        _credentials_ready=Mock(return_value=True), _starting_ots=set(),
        status=Mock(), _start_task=Mock(), _workorder_started=Mock(),
        workorder_started=SimpleNamespace(emit=Mock()), ot_sessions=[],
    )


class WorkorderStartUiTests(TestCase):
    def test_settings_load_and_save_the_opt_in_control(self):
        app = QApplication.instance() or QApplication([])
        class SettingsWindow(MaximoDesktopWindow):
            def __init__(self):
                QMainWindow.__init__(self)
                self.cfg = AppConfig()
                self.status = Mock()
                for name in ('schedule_auto_update', '_refresh_auto_update_summary', '_refresh_app_update_block',
                             '_refresh_reconciliation_summary', '_refresh_fault_description_summary',
                             '_update_fault_description_controls', '_refresh_priorities', 'refresh_table'):
                    setattr(self, name, Mock())
                self.setCentralWidget(self._build_settings_page())
                self._load_config()
        ui = SettingsWindow()
        try:
            self.assertFalse(ui.workorder_start_check.isChecked())
            self.assertFalse(ui.settings_dirty())
            ui.workorder_start_check.setChecked(True)
            self.assertTrue(ui.settings_dirty())
            with patch('ui_qt.save_config') as save:
                ui.save_settings(show_feedback=False)
            self.assertTrue(save.call_args.args[0].workorder_start_enabled)
            self.assertFalse(ui.settings_dirty())
        finally:
            ui.deleteLater()
            app.processEvents()

    def test_open_only_keeps_its_visible_browser_without_starting(self):
        ui = window()
        with patch('ui_qt.open_ot') as open_ot, patch('ui_qt.start_ot') as start:
            MaximoDesktopWindow.open_ot_number(ui, '4314531')
            ui._start_task.call_args.args[0]()
        self.assertFalse(open_ot.call_args.kwargs['headless'])
        self.assertNotIn('start_workflow', open_ot.call_args.kwargs)
        start.assert_not_called()

    def test_disabled_start_never_enqueues_a_task(self):
        ui = window(enabled=False)
        MaximoDesktopWindow.start_ot_number(ui, '4314531')
        ui._start_task.assert_not_called()

    def test_headless_start_is_explicit_reports_progress_and_deduplicates(self):
        ui, report = window(), Mock()
        result = {'ot':'4314531','status':'INPRG','already_started':False}
        with patch('ui_qt.start_ot', return_value=result) as start:
            MaximoDesktopWindow.start_ot_number(ui, '4314531')
            task = ui._start_task.call_args
            MaximoDesktopWindow.start_ot_number(ui, '4314531')
            ui._start_task.assert_called_once()
            self.assertEqual(task.args[0](report), result)
            start.assert_called_once_with('4314531', progress_callback=report)
            task.kwargs['progress']('Configurando RFN-70')
            ui.status.showMessage.assert_called_with('Configurando RFN-70')
            task.args[1](result)
        self.assertEqual(ui._starting_ots, set())
        ui._workorder_started.assert_called_once_with(result)

    def test_failed_start_releases_its_guard_without_reporting_success(self):
        ui = window()
        MaximoDesktopWindow.start_ot_number(ui, '4314531')
        failed = ui._start_task.call_args.args[2]
        with patch('ui_qt.QMessageBox.critical') as error:
            failed('Aviso desconocido')
        self.assertEqual(ui._starting_ots, set())
        ui._workorder_started.assert_not_called()
        error.assert_called_once_with(ui, 'Iniciar OT 4314531', 'Aviso desconocido')
