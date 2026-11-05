"""Warehouse prototype UI, using only local data and no Edge session."""
import json
from pathlib import Path
import time
from unittest import TestCase
from unittest.mock import Mock, patch

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QTableWidget, QTableWidgetItem

from config import AppConfig
from tests.test_support import temporary_directory
from tests.test_ui_workorder_start import settings_window
from warehouse import WarehouseItem
from warehouse_ui import WarehouseBatchDialog, WarehouseWindowMixin


class Host(WarehouseWindowMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = AppConfig(warehouse_enabled=True)
        self.table = QTableWidget(4, 8, self)
        for row in range(4):
            for column in range(8):
                value = f'DEMO-{row}' if column == 1 else 'WAPPR' if column == 7 else ''
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.open_ot_number = Mock()


class WarehouseUiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, condition):
        deadline = time.monotonic() + 8
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(15)
        self.assertTrue(condition())

    def select_rows(self, host, rows):
        for row in rows:
            host.table.selectionModel().select(host.table.model().index(row, 0),
                QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def test_setting_load_save_and_disabled_menu(self):
        window = settings_window()
        host = Host()
        try:
            self.assertFalse(window.warehouse_check.isChecked())
            window.warehouse_check.setChecked(True)
            self.assertTrue(window.settings_dirty())
            with patch('ui_qt.save_config') as save:
                window.save_settings(show_feedback=False)
            self.assertTrue(save.call_args.args[0].warehouse_enabled)
            self.assertFalse(window.settings_dirty())
            menu = QMenu()
            host.cfg.warehouse_enabled = False
            host.add_warehouse_actions(menu)
            self.assertFalse(menu.actions())
        finally:
            host.deleteLater(); window.deleteLater(); self.app.processEvents()

    def test_right_click_preserves_multiple_rows_but_replaces_selection_outside_it(self):
        host = Host()
        try:
            self.select_rows(host, (0, 1))
            host.prepare_warehouse_context_selection(host.table.model().index(1, 2))
            self.assertEqual([item.ot for item in host.warehouse_items()], ['DEMO-0', 'DEMO-1'])
            host.prepare_warehouse_context_selection(host.table.model().index(3, 2))
            self.assertEqual([item.ot for item in host.warehouse_items()], ['DEMO-3'])
        finally:
            host.deleteLater(); self.app.processEvents()

    def test_hidden_rows_are_excluded_and_menu_freezes_ot_ids_before_table_changes(self):
        host = Host()
        try:
            self.select_rows(host, (0, 1, 2))
            host.table.setRowHidden(1, True)
            menu = QMenu()
            host.open_warehouse_batch = Mock()
            host.add_warehouse_actions(menu)
            actions = [action for action in menu.actions() if not action.isSeparator()]
            self.assertEqual(len(actions), 2)
            self.assertIn('2 OT', actions[0].text())
            host.table.item(0, 1).setText('CHANGED')
            actions[0].trigger()
            batch, action = host.open_warehouse_batch.call_args.args
            self.assertEqual([item.ot for item in batch], ['DEMO-0', 'DEMO-2'])
            self.assertEqual(action, 'receive')
        finally:
            host.deleteLater(); self.app.processEvents()

    def test_batch_requires_start_and_can_open_ot_without_submitting_any_action(self):
        opened = Mock()
        dialog = WarehouseBatchDialog([WarehouseItem('DEMO-1', status='WAPPR')], 'receive', opened)
        try:
            self.assertFalse(dialog.is_running())
            self.assertFalse(dialog._has_started)
            dialog._open_row(0, 0)
            opened.assert_called_once_with('DEMO-1')
            self.assertIsNone(dialog._worker)
        finally:
            dialog.deleteLater(); self.app.processEvents()

    def test_worker_reports_all_outcomes_and_keeps_uncertain_item_without_retry(self):
        with temporary_directory() as folder:
            dialog = WarehouseBatchDialog([WarehouseItem(f'DEMO-{i}', status='WAPPR') for i in range(4)],
                                          'receive', Mock(), report_folder=folder)
            dialog.show()
            try:
                dialog.scenario.setCurrentIndex(dialog.scenario.findData('incidents'))
                from warehouse import run_simulation as simulate
                def fast(*args, **kwargs):
                    return simulate(*args, **kwargs, delay=0.01)
                with patch('warehouse_ui.run_simulation', side_effect=fast):
                    dialog.start_simulation()
                    self.wait_for(lambda: dialog.report_path is not None and not dialog.is_running())
                self.assertEqual([r.status for r in dialog.results], ['success', 'failed', 'uncertain', 'stopped'])
                self.assertEqual(dialog.progress_bar.value(), 3)
                self.assertIn('1 sin procesar', dialog.summary.text())
                self.assertFalse(dialog.start_button.isEnabled())
                data = json.loads(Path(dialog.report_path).read_text(encoding='utf-8'))
                self.assertTrue(data['simulation'])
                self.assertEqual(dialog.table.item(1, 4).foreground().color().name(), '#dc2626')
            finally:
                dialog.close(); dialog.deleteLater(); self.app.processEvents()

    def test_close_or_escape_requests_stop_but_does_not_destroy_running_worker(self):
        with temporary_directory() as folder:
            dialog = WarehouseBatchDialog([WarehouseItem(f'DEMO-{i}', status='WAPPR') for i in range(4)],
                                          'receive', Mock(), report_folder=folder)
            dialog.show()
            try:
                from warehouse import run_simulation as simulate
                def fast(*args, **kwargs):
                    return simulate(*args, **kwargs, delay=0.02)
                with patch('warehouse_ui.run_simulation', side_effect=fast):
                    dialog.start_simulation()
                    self.wait_for(lambda: any(r.status == 'running' for r in dialog.results))
                    dialog.close()
                    dialog.reject()
                    self.assertTrue(dialog.isVisible())
                    self.wait_for(lambda: dialog.report_path is not None and not dialog.is_running())
                self.assertEqual(dialog.results[0].status, 'success')
                self.assertTrue(all(r.status == 'stopped' for r in dialog.results[1:]))
            finally:
                dialog.close(); dialog.deleteLater(); self.app.processEvents()
