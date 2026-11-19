"""Read-only UI usability and cooperative preview closure, no live sessions."""
import tests
from threading import Event
from unittest import TestCase
from unittest.mock import Mock,patch
from PySide6.QtCore import QThread,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QHeaderView
from failure_catalog import default_selection
from warehouse import WarehouseItem
from technician_sat_ui import TechnicianSatDialog
from technician_repair_ui import RepairDialog


class PendingRead(QThread):
    def __init__(self,parent,plan=None):
        super().__init__(parent);self.plan=plan;self.stop_requested=Event();self.entered=Event();self.release=Event()
    def run(self):
        self.entered.set();self.release.wait(3)


class SatReviewUsabilityTests(TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def sat(self):
        item=WarehouseItem('1234567',equipment='LONG EQUIPMENT DESCRIPTION THAT IS WIDER THAN THE CELL',serial='NS-ABC-123456789')
        with patch('technician_sat_ui.get_fault_description',return_value='LOCAL FAULT'),patch('technician_sat_ui.fault_description_checked',return_value=True):
            d=TechnicianSatDialog([item],Mock(),selection=default_selection(),autoload=False)
        self.addCleanup(d.deleteLater);return d

    def read(self,d):
        worker=PendingRead(d);worker.start();self.assertTrue(worker.entered.wait(1))
        self.addCleanup(lambda:(worker.release.set(),worker.wait(2000),self.app.processEvents()))
        return worker

    def test_local_fault_is_visible_before_any_maximo_preview(self):
        d=self.sat()
        self.assertEqual(d.inputs['1234567']['reason'].text(),'LOCAL FAULT')
        self.assertIsNone(d._preview_worker)
        self.assertFalse(d.start_button.isEnabled())

    def test_serial_is_on_first_line_with_full_text_tooltip_and_resizable_rows_columns(self):
        d=self.sat();cell=d.table.item(0,1)
        self.assertEqual(cell.text().splitlines()[0],'N/S: NS-ABC-123456789')
        self.assertEqual(cell.toolTip(),cell.text())
        self.assertFalse(d.table.verticalHeader().isHidden())
        self.assertEqual(d.table.verticalHeader().sectionResizeMode(0),QHeaderView.Interactive)
        self.assertGreaterEqual(d.table.rowHeight(0),68)
        d.table.setRowHeight(0,120);self.assertEqual(d.table.rowHeight(0),120)
        for col in (0,1,2,6,7,8):self.assertEqual(d.table.horizontalHeader().sectionResizeMode(col),QHeaderView.Interactive)
        field=d.inputs['1234567']['incident'];field.setText('long free text incident reference')
        self.assertIn(field.text(),field.toolTip())

    def test_manual_edits_and_explicit_clears_survive_late_preview(self):
        d=self.sat();field=d.inputs['1234567']['reason']
        field.selectAll();QTest.keyClick(field,Qt.Key_Backspace)
        d._defaults_ready({'1234567':{'reason':'SERVER DEFAULT','duration':'0,5','status':'APPR'}})
        self.assertEqual(field.text(),'')
        self.assertIn('Propuesta (MD)',field.toolTip())

    def test_sat_preview_close_hides_now_and_keeps_live_thread_until_cleanup(self):
        d=self.sat();worker=self.read(d);d._preview_worker=worker
        d.show();self.app.processEvents();self.assertTrue(d.close())
        self.assertFalse(d.isVisible());self.assertTrue(worker.stop_requested.is_set())
        self.assertTrue(worker.isRunning());self.assertIn(d,self.app._md_cancelled_previews)
        d._defaults_ready({'1234567':{'reason':'Late','duration':'1','status':'APPR'}})
        self.assertFalse(d.start_button.isEnabled())
        worker.release.set();worker.wait(2000);self.app.processEvents()
        self.assertNotIn(d,self.app._md_cancelled_previews)

    def test_sat_escape_cancels_preview_but_real_submission_stays_protected(self):
        d=self.sat();worker=self.read(d);d._preview_worker=worker
        d.show();d.reject();self.assertFalse(d.isVisible());self.assertTrue(worker.stop_requested.is_set())
        real=self.sat();running=self.read(real);real._worker=running
        real.show();self.app.processEvents();self.assertFalse(real.close())
        self.assertTrue(real.isVisible());self.assertTrue(running.stop_requested.is_set())

    def test_repair_preview_can_close_but_executing_repair_cannot(self):
        with patch('technician_repair_ui.get_fault_description',return_value='LOCAL'):
            d=RepairDialog(WarehouseItem('1234567'),default_selection(),autoload=False)
            real=RepairDialog(WarehouseItem('1234568'),default_selection(),autoload=False)
        self.addCleanup(d.deleteLater);self.addCleanup(real.deleteLater)
        worker=self.read(d);d._worker=worker;d.show();self.assertTrue(d.close())
        self.assertFalse(d.isVisible());self.assertTrue(worker.stop_requested.is_set())
        running=self.read(real);running.plan=object();real._worker=running
        real.show();self.app.processEvents();self.assertFalse(real.close())
        self.assertTrue(real.isVisible());self.assertTrue(running.stop_requested.is_set())

    def test_sat_defaults_use_local_fault_but_still_validate_current_state_and_hours(self):
        from technician_sat import technician_sat_defaults
        session=Mock();session.open.return_value='APPR'
        session.identity.return_value={'Activo':'A','Planta':'LAB','Nº de serie':'S'}
        session.reader.value.return_value='0,50'
        with patch('technician_sat.get_fault_description',return_value='Cached fault'):
            data=technician_sat_defaults([WarehouseItem('1234567',serial='S')],session_factory=lambda:session)
        self.assertEqual(data['1234567']['reason'],'Cached fault')
        session.reader.value.assert_called_once_with('Horas totales de reparación')
        session.open.assert_called_once_with('1234567');session.close.assert_called_once()

    def test_successfully_checked_empty_fault_is_not_read_again(self):
        from technician_sat import technician_sat_defaults
        session=Mock();session.open.return_value='APPR'
        session.identity.return_value={'Activo':'A','Planta':'LAB','Nº de serie':'S'}
        session.reader.value.return_value='0,25'
        with patch('technician_sat.get_fault_description',return_value=''),patch('technician_sat.fault_description_checked',return_value=True):
            data=technician_sat_defaults([WarehouseItem('1234567',serial='S')],session_factory=lambda:session)
        self.assertEqual(data['1234567']['reason'],'')
        session.reader.value.assert_called_once_with('Horas totales de reparación')

    def test_closing_before_scheduled_preview_prevents_a_late_worker_start(self):
        sat=self.sat();sat.close()
        with patch('technician_sat_ui.TechnicianPreviewThread') as worker:sat.start_preview()
        worker.assert_not_called()
        with patch('technician_repair_ui.get_fault_description',return_value='LOCAL'):
            repair=RepairDialog(WarehouseItem('1234567'),default_selection(),autoload=False)
        self.addCleanup(repair.deleteLater);repair.close()
        with patch('technician_repair_ui.RepairWorker') as worker:repair.launch()
        worker.assert_not_called()
