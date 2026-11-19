import tests
from unittest import TestCase
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication, QMessageBox, QMenu
from config import AppConfig
from failure_catalog import default_selection
from technician_sat_ui import TechnicianSatDialog
from warehouse import WarehouseItem
from tests.test_warehouse_ui import Host


class TechnicianSatUiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def dialog(self):
        dialog=TechnicianSatDialog([WarehouseItem('1')],Mock(),selection=default_selection(),autoload=False)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_open_review_alone_has_no_worker_or_submission(self):
        dialog=self.dialog()
        self.assertIsNone(dialog._worker);self.assertIsNone(dialog._preview_worker)
        self.assertFalse(dialog.start_button.isEnabled())
        self.assertFalse(dialog._has_started)

    def test_fresh_fault_is_default_but_manual_reason_is_not_overwritten(self):
        dialog=self.dialog()
        defaults={'1':{'reason':'NO ADMITE','duration':'0,50','status':'APPR'}}
        dialog._defaults_ready(defaults)
        self.assertEqual(dialog.inputs['1']['reason'].text(),'NO ADMITE')
        dialog.inputs['1']['reason'].setText('Motivo revisado')
        dialog._defaults_ready(defaults)
        self.assertEqual(dialog.inputs['1']['reason'].text(),'Motivo revisado')

    def test_stock_reference_and_explicit_confirmation_before_batch(self):
        dialog=self.dialog()
        dialog._defaults_ready({'1':{'reason':'NO ADMITE','duration':'0,50','status':'APPR'}})
        dialog.inputs['1']['incident'].setText('stock')
        with patch.object(dialog,'_launch_worker') as launch,patch('warehouse_ui.QMessageBox.question',return_value=QMessageBox.No):
            dialog.start_operation()
        launch.assert_not_called()
        with patch.object(dialog,'_launch_worker') as launch,patch('warehouse_ui.QMessageBox.question',return_value=QMessageBox.Yes):
            dialog.start_operation()
        launch.assert_called_once()
        self.assertEqual(dialog.technician_plans[0].incident_summary,'inc: stock')
        self.assertEqual(dialog.technician_plans[0].reason,'NO ADMITE')

    def test_missing_reference_never_opens_confirmation_or_worker(self):
        dialog=self.dialog()
        dialog._defaults_ready({'1':{'reason':'NO ADMITE','duration':'0,50','status':'APPR'}})
        with patch.object(dialog,'_launch_worker') as launch,patch('warehouse_ui.QMessageBox.question') as question,patch('technician_sat_ui.QMessageBox.warning'):
            dialog.start_operation()
        launch.assert_not_called();question.assert_not_called()

    def test_technical_option_is_independent_of_warehouse_flag(self):
        self.assertFalse(AppConfig().technician_sat_enabled)
        host=Host();self.addCleanup(host.deleteLater)
        host.cfg=AppConfig(warehouse_enabled=False,technician_sat_enabled=True)
        host.table.selectRow(0)
        menu=QMenu();host.add_technician_sat_action(menu)
        self.assertTrue(any('Técnico' in a.text() for a in menu.actions()))
        other=QMenu();host.add_warehouse_actions(other)
        self.assertFalse(other.actions())


    def test_real_incompatible_state_disables_submission_before_data_entry(self):
        dialog=self.dialog()
        dialog._defaults_ready({'1':{'reason':'NO ADMITE','duration':'0,50','status':'ISSUE'}})
        self.assertFalse(dialog.start_button.isEnabled())
        self.assertIn('no están en APPR',dialog.current_step.text())


    def test_review_reserves_visible_space_for_all_editable_fields(self):
        dialog=self.dialog()
        for column in (6,7,8):self.assertFalse(dialog.table.isColumnHidden(column))
        for column in (3,4,5):self.assertTrue(dialog.table.isColumnHidden(column))
