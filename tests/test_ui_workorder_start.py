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
        _credentials_ready=Mock(return_value=True),
        status=Mock(), _start_task=Mock(), _workorder_started=Mock(),
        workorder_started=SimpleNamespace(emit=Mock()), ot_sessions=[],
        workorder_closed=SimpleNamespace(emit=Mock()),
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
            self.assertFalse(ui.workorder_close_check.isChecked())
            self.assertFalse(ui.settings_dirty())
            ui.workorder_start_check.setChecked(True)
            ui.workorder_close_check.setChecked(True)
            self.assertTrue(ui.settings_dirty())
            with patch('ui_qt.save_config') as save:
                ui.save_settings(show_feedback=False)
            self.assertTrue(save.call_args.args[0].workorder_start_enabled)
            self.assertTrue(save.call_args.args[0].workorder_close_enabled)
            self.assertFalse(ui.settings_dirty())
        finally:
            ui.deleteLater()
            app.processEvents()

    def test_open_only_keeps_its_visible_browser_without_starting(self):
        ui = window()
        with patch('ui_qt.open_ot') as open_ot:
            MaximoDesktopWindow.open_ot_number(ui, '4314531')
            ui._start_task.call_args.args[0]()
        self.assertFalse(open_ot.call_args.kwargs['headless'])
        self.assertNotIn('start_workflow', open_ot.call_args.kwargs)

    def test_desktop_context_menu_only_opens_workorders_and_does_not_start_them(self):
        ui = window()
        ui.table = Mock()
        ui.table.indexAt.return_value.row.return_value = 0
        ui.table.indexAt.return_value.column.return_value = 1
        ui.table.item.side_effect = lambda row,col: SimpleNamespace(text=lambda: 'APPR' if col==7 else 'Activo')
        ui.selected_ot = Mock(return_value='4314531')
        menu = Mock()
        with patch('ui_qt.QMenu',return_value=menu):
            MaximoDesktopWindow.show_context_menu(ui, Mock())
        labels = [call.args[0] for call in menu.addAction.call_args_list]
        self.assertIn('Abrir OT en Maximo',labels)
        self.assertNotIn('Iniciar OT',labels)
        self.assertNotIn('Cerrar OT',labels)
        self.assertFalse(hasattr(MaximoDesktopWindow,'start_ot_number'))
