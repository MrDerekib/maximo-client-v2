import tests
import json
from dataclasses import asdict
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from operations_history import read_operations
from tests import test_filters as fixtures
from tests import test_repair_recovery as repairs
from warehouse import WarehouseItem
from warehouse_recovery import RecoveryStore


class OperationsHistoryTests(TestCase):
    def setUp(self):
        self.fixture = fixtures.FilterTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = RecoveryStore(Path(self.fixture.temp_path) / 'operations')
        self.identity = {'Activo': 'A-1', 'Nº de serie': 'S-1', 'Planta': 'LAB'}

    def test_history_prefers_pending_and_archived_evidence_over_old_result(self):
        record = self.store.begin(WarehouseItem('1'), 'technician_close', self.identity,
                                  'INPRG', preparing=True)
        report = self.store.folder.parent / 'repair-result.json'
        report.write_text(json.dumps({'action': 'technician_close', 'results': [
            {'item': {'ot': '1'}, 'operation_id': record['operation_id'], 'status': 'uncertain'},
            {'item': {'ot': '2'}, 'operation_id': 'completed', 'status': 'success', 'verified_status': 'ISSUE'},
        ]}), encoding='utf-8')

        history = read_operations(self.store, self.store.pending(), history=True)
        self.assertEqual([(row.ot, row.pending) for row in history], [('1', True), ('2', False)])
        self.assertTrue(self.store.archive_external_close(record, lambda *_: True))
        self.assertEqual(read_operations(self.store, self.store.pending()), [])
        history = {row.ot: row for row in read_operations(self.store, self.store.pending(), history=True)}
        self.assertEqual(history['1'].result, 'Resuelta por otra vía')
        self.assertEqual(history['1'].state, 'CLOSE')
        self.assertEqual(history['2'].state, 'ISSUE')

    def test_list_opens_pending_view_and_rechecks_only_the_selected_attempt(self):
        self.store.begin(WarehouseItem('1'), 'dispatch', self.identity, 'ISSUE')
        with patch('warehouse_ui.RecoveryStore', return_value=self.store), \
                self.fixture.qt_window() as (window, _):
            window.cfg.warehouse_enabled = True
            window._refresh_operations()
            self.assertEqual(window.operations_button.text(), 'Operaciones · 1 pendiente')
            with patch('warehouse_ui.WarehouseBatchDialog.start_reverification') as recheck:
                window.operations_button.click()
                dialog = window._operations_dialog
                self.assertEqual(dialog.view.currentText(), 'Pendientes')
                self.assertEqual(dialog.table.item(0, 1).text(), '1')
                dialog.retry_button.click()
                review = window._warehouse_dialogs[-1]
                self.assertEqual([item.ot for item in review.items], ['1'])
                recheck.assert_called_once()
                review.close()
                dialog.close()

    def test_technical_recovery_restores_reviewed_form_before_recheck(self):
        plan = repairs.plan()
        self.store.begin(plan.item, 'technician_close', repairs.IDENTITY, 'INPRG',
                         preparing=True, reviewed_request=asdict(plan))
        with patch('warehouse_ui.RecoveryStore', return_value=self.store), \
                patch('technician_repair_ui.RecoveryStore', return_value=self.store), \
                self.fixture.qt_window() as (window, _):
            window.cfg.workorder_close_enabled = True
            with patch('technician_repair_ui.RepairDialog.recheck_repair') as recheck:
                window.operations_button.click()
                history = window._operations_dialog
                history.retry_button.click()
                repair = window._warehouse_dialogs[-1]
                self.assertEqual(repair.reference.text(), plan.reference)
                self.assertEqual(repair.duration.text(), plan.duration)
                self.assertEqual(repair.entries.item(0, 0).text(), plan.entries[0].summary)
                self.assertFalse(repair.submit.isEnabled())
                recheck.assert_called_once()
                repair.progress_dialog.close()
                repair.close()
                history.close()
