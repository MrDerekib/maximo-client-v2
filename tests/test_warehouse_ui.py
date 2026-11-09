"""Warehouse prototype UI, using only local data and no Edge session."""
import tests  # Isolate application data before importing product modules.
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
from warehouse import ACTIONS, RECEIPT_ACTIONS, WarehouseItem
from warehouse_ui import WarehouseBatchDialog, WarehouseWindowMixin
from workorder_selection import prepare_row_context_selection


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
    def test_verified_status_is_persisted_with_action_specific_tracking(self):
        from warehouse import WarehouseResult
        from warehouse_ui import WarehouseThread, LOCAL_TRACKING
        from warehouse_transport import FINAL_STATES
        for action, tracking in LOCAL_TRACKING.items():
            with temporary_directory() as folder:
                worker=WarehouseThread([WarehouseItem('1')],action,Path(folder)/'events.jsonl')
                changed=[]; finished=[]
                worker.record_updated.connect(lambda ot,status:changed.append((ot,status)))
                worker.completed.connect(finished.append)
                def run(items, action, **kwargs):
                    rows=tuple(WarehouseResult(items[0],status=status,verified_status=FINAL_STATES[action] if status=='success' else '')
                               for status in ('success','failed','uncertain','stopped'))
                    for index,result in enumerate(rows):kwargs['progress'](index,result)
                    return rows
                with patch('warehouse_transport.run_live',side_effect=run), patch('db.apply_warehouse_status',return_value=True) as save:
                    worker.run()
                save.assert_called_once_with('1',tracking)
                self.assertEqual(changed,[('1',tracking)])
                self.assertEqual(finished[0][0].status,'success')

    def test_local_write_error_preserves_remote_success_and_explains_local_failure(self):
        from warehouse import WarehouseResult
        from warehouse_ui import WarehouseThread
        with temporary_directory() as folder:
            worker=WarehouseThread([WarehouseItem('1')],'receive',Path(folder)/'events.jsonl')
            changed=[];finished=[]
            worker.record_updated.connect(lambda *args:changed.append(args));worker.completed.connect(finished.append)
            def run(items,action,**kwargs):
                r=WarehouseResult(items[0],status='success',verified_status='APPR')
                kwargs['progress'](0,r);return (r,)
            with patch('warehouse_transport.run_live',side_effect=run), patch('db.apply_warehouse_status',side_effect=OSError('disk')):
                worker.run()
            self.assertEqual(changed,[])
            self.assertEqual(finished[0][0].status,'success')
            self.assertIn('copia local',finished[0][0].detail)

    def test_row_refresh_updates_one_cell_and_removes_it_when_filter_no_longer_matches(self):
        from tests.test_ui_app_updates import MaximoDesktopWindow
        host=Host()
        host.search_edit=Mock();host.search_edit.text.return_value=''
        host.search_field=Mock(return_value='OT');host.effective_advanced_filters=Mock(return_value={})
        host.filter_choices_cache={'tracking':[]};host._update_list_summary=Mock();host.refresh_table=Mock()
        try:
            untouched=host.table.item(1,2)
            with patch('ui_qt.fetch_data',return_value=[('DEMO-0','','','','','','SAT EXT','')]):
                MaximoDesktopWindow.warehouse_row_updated(host,'DEMO-0','SAT EXT')
            self.assertEqual(host.table.item(0,7).text(),'SAT EXT')
            self.assertIs(host.table.item(1,2),untouched)
            host.refresh_table.assert_not_called()
            with patch('ui_qt.fetch_data',return_value=[('DEMO-0','','','','','','CLOSE','')]):
                MaximoDesktopWindow.warehouse_row_updated(host,'DEMO-0','SAT EXT')
            self.assertEqual(host.table.item(0,7).text(),'CLOSE')
            with patch('ui_qt.fetch_data',return_value=[]):
                MaximoDesktopWindow.warehouse_row_updated(host,'DEMO-0','SAT EXT')
            self.assertEqual(host.table.rowCount(),3)
            self.assertEqual(host.table.item(0,1).text(),'DEMO-1')
        finally:
            host.deleteLater();self.app.processEvents()

    def test_sat_details_are_optional_per_ot_and_hidden_by_default(self):
        items = [WarehouseItem('1'), WarehouseItem('2')]
        for action in ('receive_sat_external', 'receive_sat_internal'):
            for enabled in (False, True):
                dialog = WarehouseBatchDialog(items, action, Mock(), ask_sat_details=enabled)
                try:
                    self.assertEqual(set(dialog.details_inputs), {'1','2'} if enabled else set())
                    if enabled:
                        dialog.details_inputs['1'].setText('Detalle OT 1')
                        self.assertEqual(dialog.details_inputs['2'].text(), '')
                    self.assertFalse(dialog._has_started)
                finally:
                    dialog.deleteLater(); self.app.processEvents()

    def setUp(self):
        patcher = patch('warehouse_ui.WAREHOUSE_DEVELOPMENT_MODE', False, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cancel_confirmation_never_creates_worker(self):
        from PySide6.QtWidgets import QMessageBox
        dialog = WarehouseBatchDialog([WarehouseItem('1')], 'receive', Mock())
        try:
            self.assertFalse(hasattr(dialog, 'mode'))
            self.assertFalse(hasattr(dialog, 'scenario'))
            with patch('warehouse_ui.QMessageBox.question', return_value=QMessageBox.No), patch('warehouse_ui.WarehouseThread') as worker:
                dialog.start_operation()
            worker.assert_not_called()
            self.assertFalse(dialog._has_started)
        finally:
            dialog.deleteLater(); self.app.processEvents()

    def test_unvalidated_actions_cannot_open_or_start(self):
        for action in ('reject_receive',):
            with self.assertRaises(ValueError):
                WarehouseBatchDialog([WarehouseItem('1')], action, Mock())
        host = Host()
        try:
            self.select_rows(host, (0,))
            menu = QMenu(); host.add_warehouse_actions(menu)
            receipt = next(a.menu() for a in menu.actions() if a.menu())
            self.assertEqual([a.isEnabled() for a in receipt.actions()], [True, False, True, True])
            self.assertNotIn('simulación', ' '.join(a.text() for a in menu.actions()))
        finally:
            host.deleteLater(); self.app.processEvents()

    def test_progress_and_report_preserve_all_outcomes(self):
        from dataclasses import replace
        from warehouse import WarehouseResult
        from PySide6.QtWidgets import QMessageBox
        with temporary_directory() as folder:
            dialog = WarehouseBatchDialog([WarehouseItem(str(i)) for i in range(4)], 'receive', Mock(), report_folder=Path(folder))
            def run(items, action, **kwargs):
                results = []
                for index, status in enumerate(('success','failed','uncertain','success')):
                    r = WarehouseResult(items[index], status=status, step='Completado', detail=status,
                        completed_steps=5 if status=='success' else 3, verified_status='APPR' if status=='success' else '')
                    kwargs['progress'](index,r); results.append(r)
                return tuple(results)
            try:
                with patch('warehouse_ui.QMessageBox.question', return_value=QMessageBox.Yes), patch('warehouse_transport.run_live', side_effect=run), patch('db.apply_warehouse_status',return_value=True):
                    dialog.start_operation()
                    self.wait_for(lambda:dialog.report_path is not None and not dialog.is_running())
                self.assertEqual([r.status for r in dialog.results], ['success','failed','uncertain','success'])
                self.assertFalse(json.loads(dialog.report_path.read_text(encoding='utf-8'))['simulation'])
                self.assertEqual(dialog.table.item(0,4).text(),'Operación verificada')
                self.assertEqual(dialog.progress_bar.value(),4)
                self.assertFalse(dialog.start_button.isEnabled())
            finally:
                dialog.deleteLater();self.app.processEvents()

    def test_close_requests_stop_while_worker_remains_alive(self):
        dialog = WarehouseBatchDialog([WarehouseItem('1')], 'receive', Mock())
        worker = Mock(); worker.isRunning.return_value=True
        dialog._worker=worker
        try:
            dialog.reject()
            worker.stop_requested.set.assert_called_once()
        finally:
            worker.isRunning.return_value=False
            dialog._worker=None
            dialog.deleteLater();self.app.processEvents()

    def test_optional_details_setting_defaults_off_and_is_saved(self):
        window = settings_window()
        try:
            self.assertFalse(window.cfg.warehouse_ask_sat_details)
            self.assertFalse(window.warehouse_details_check.isChecked())
            window.warehouse_details_check.setChecked(True)
            self.assertTrue(window.settings_dirty())
            with patch('ui_qt.save_config') as save:
                window.save_settings(show_feedback=False)
            self.assertTrue(save.call_args.args[0].warehouse_ask_sat_details)
        finally:
            window.deleteLater()
            self.app.processEvents()




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
            prepare_row_context_selection(host.table, host.table.model().index(1, 2))
            self.assertEqual([item.ot for item in host.warehouse_items()], ['DEMO-0', 'DEMO-1'])
            prepare_row_context_selection(host.table, host.table.model().index(3, 2))
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
            receipt_actions = actions[0].menu().actions()
            self.assertEqual(len(receipt_actions), 4)
            host.table.item(0, 1).setText('CHANGED')
            receipt_actions[0].trigger()
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

    def test_standard_installation_exposes_enabled_actions_and_opens_review_only(self):
        host=Host()
        try:
            self.select_rows(host,(0,1))
            with patch('warehouse_ui.WarehouseThread') as worker:
                for enabled in (False,True):
                    host.cfg.warehouse_enabled=enabled
                    menu=QMenu()
                    host.add_warehouse_actions(menu)
                    self.assertEqual(bool(menu.actions()),enabled)
                    if enabled:
                        receipt=next(action.menu() for action in menu.actions() if action.menu())
                        receipt.actions()[0].trigger()
                        self.assertEqual(len(host._warehouse_dialogs),1)
                        dialog=host._warehouse_dialogs[0]
                        self.assertTrue(dialog.isVisible())
                        self.assertEqual([item.ot for item in dialog.items],['DEMO-0','DEMO-1'])
                        self.assertFalse(dialog._has_started)
                        self.assertIsNone(dialog._worker)
                worker.assert_not_called()
                host.cfg.warehouse_enabled=False
                host.open_warehouse_batch(host.warehouse_items(),'receive')
                self.assertEqual(len(host._warehouse_dialogs),1)
        finally:
            for dialog in getattr(host,'_warehouse_dialogs',[]):dialog.close()
            host.deleteLater();self.app.processEvents()
