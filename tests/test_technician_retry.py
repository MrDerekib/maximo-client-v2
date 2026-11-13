import tests
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QMessageBox
from warehouse import WarehouseItem,WarehouseResult
from warehouse_recovery import RecoveryStore,preparation_retry_allowed
from warehouse_transport import run_live,reverify_pending
from technician_sat import reviewed_sat_plans,saved_request
from technician_sat_ui import TechnicianSatDialog
from warehouse_ui import WarehouseBatchDialog
from failure_catalog import default_selection
from tests.test_support import temporary_directory
from tests.test_warehouse_recovery import FakeServer


class TechnicianRetryTests(TestCase):
    def setUp(self):
        self.temp=temporary_directory();self.folder=Path(self.temp.__enter__())
        self.addCleanup(self.temp.__exit__,None,None,None)
        self.store=RecoveryStore(self.folder)
        self.item=WarehouseItem('1',serial='SERIAL-1')
        self.plan,=reviewed_sat_plans([self.item],{'1':{'duration':'0,50','incident':'stock','reason':'Real reason'}},default_selection())
        self.identity={'Activo':'ASSET-1','Nº de serie':'SERIAL-1','Planta':'LAB-BAD'}

    def record(self,save_request=True):
        return self.store.begin(self.item,'technician_sat_external',self.identity,'APPR',preparing=True,
            reviewed_request=saved_request(self.plan) if save_request else None)

    def test_reviewed_inputs_survive_store_reopening(self):
        record=self.record()
        reloaded=RecoveryStore(self.folder).get('1')
        self.assertEqual(reloaded['reviewed_request'],saved_request(self.plan))
        self.assertTrue(preparation_retry_allowed(reloaded))
        self.assertEqual(reloaded['operation_id'],record['operation_id'])

    def test_only_proven_pre_route_preparations_allow_retry(self):
        record=self.record()
        for field,value in (('route_attempted',True),('confirmation_attempted',True),
                ('details_attempted',True),('phase','route_attempted'),('action','receive_sat_external')):
            changed=dict(record);changed[field]=value
            self.assertFalse(preparation_retry_allowed(changed))
        self.assertFalse(preparation_retry_allowed(None))

    def test_reviewed_retry_uses_same_claim_and_routes_once(self):
        record=self.record();server=FakeServer(action='technician_sat_external',states={'1':'APPR'})
        original=server.session
        def factory():
            session=original();session.accept_button.return_value.click.side_effect=lambda:server.sent.update(['1'])
            return session
        with patch('technician_sat.TechnicianSatPreparer') as cls:
            cls.return_value.prepare_route.return_value={'ready':True}
            result,=run_live([self.item],'technician_sat_external',technician_plans=[self.plan],
                technician_retries={'1':record['operation_id']},recovery_store=self.store,session_factory=factory)
        self.assertEqual(result.status,'success')
        self.assertEqual(result.operation_id,record['operation_id'])
        self.assertEqual(self.store.get('1')['retry_count'],1)
        self.assertEqual(server.routed['1'],1);self.assertEqual(server.details_sent['1'],1)
        self.assertEqual(len(server.sessions),1)

    def test_stale_retry_or_any_route_attempt_blocks_before_opening_browser(self):
        record=self.record();self.store.update(record,'route_attempted',route_attempted=True)
        factory=Mock()
        result,=run_live([self.item],'technician_sat_external',technician_plans=[self.plan],
            technician_retries={'1':record['operation_id']},recovery_store=self.store,
            session_factory=factory,auto_recheck=False)
        self.assertNotEqual(result.status,'success');factory.assert_not_called()

    def test_recovery_change_between_review_and_resume_is_not_overwritten(self):
        record=self.record()
        self.store.update(record,'route_attempted',route_attempted=True)
        with self.assertRaises(RuntimeError):self.store.resume_preparation(record,saved_request(self.plan))
        self.assertTrue(self.store.get('1')['route_attempted'])
        self.assertEqual(self.store.get('1')['phase'],'route_attempted')

    def test_readonly_reverification_of_incomplete_preparation_does_not_expect_issue(self):
        record=self.record();factory=Mock()
        result,=reverify_pending([record],recovery_store=self.store,session_factory=factory)
        self.assertEqual(result.status,'failed');self.assertEqual(result.completed_steps,1)
        self.assertEqual(result.step,'Preparación incompleta');factory.assert_not_called()

    def test_failure_before_route_is_reported_as_incomplete_without_auto_recheck(self):
        server=FakeServer(action='technician_sat_external',states={'1':'APPR'})
        with patch('technician_sat.TechnicianSatPreparer') as cls:
            cls.return_value.prepare.side_effect=RuntimeError('Save not verified')
            result,=run_live([self.item],'technician_sat_external',technician_plans=[self.plan],
                recovery_store=self.store,session_factory=server.session)
        self.assertEqual(result.status,'failed');self.assertEqual(result.completed_steps,1)
        self.assertTrue(preparation_retry_allowed(self.store.get('1')))
        self.assertEqual(len(server.sessions),1);self.assertFalse(server.routed)


class TechnicianRetryUiTests(TechnicianRetryTests):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def dialog(self,record):
        d=TechnicianSatDialog([self.item],Mock(),autoload=False,retry_records=[record],report_folder=self.folder,selection=default_selection())
        self.addCleanup(d.deleteLater)
        return d

    def test_review_prefills_persisted_request_but_never_launches(self):
        record=self.record();d=self.dialog(record)
        self.assertEqual(d.inputs['1']['incident'].text(),'stock')
        self.assertEqual(d.inputs['1']['reason'].text(),'Real reason')
        self.assertEqual(d.technician_retries,{'1':record['operation_id']})
        self.assertFalse(d.start_button.isEnabled());self.assertIsNone(d._worker)
        d._defaults_ready({'1':{'duration':'1,00','reason':'Current fault','incident':'other','status':'APPR'}})
        self.assertEqual(d.inputs['1']['reason'].text(),'Real reason')
        self.assertIn('Current fault',d.inputs['1']['reason'].toolTip())
        with patch.object(d,'_launch_worker') as launch,patch('warehouse_ui.QMessageBox.question',return_value=QMessageBox.No):
            d.start_operation()
        launch.assert_not_called();self.assertEqual(self.store.get('1'),record)

    def test_legacy_record_can_be_reviewed_without_invented_inputs(self):
        d=self.dialog(self.record(False))
        self.assertEqual(d.inputs['1']['incident'].text(),'')
        d._defaults_ready({'1':{'duration':'0,50','reason':'Actual fault','incident':'stock','status':'APPR'}})
        self.assertEqual(d.inputs['1']['incident'].text(),'stock')
        with patch.object(d,'_launch_worker') as launch,patch('warehouse_ui.QMessageBox.question',return_value=QMessageBox.Yes):d.start_operation()
        launch.assert_called_once()

    def test_changed_live_status_disables_retry(self):
        d=self.dialog(self.record())
        d._defaults_ready({'1':{'duration':'0,50','reason':'Fault','status':'ISSUE'}})
        self.assertFalse(d.start_button.isEnabled())
        with patch.object(d,'_launch_worker') as launch:d.start_operation()
        launch.assert_not_called()

    def test_completed_preparation_report_does_not_tick_unexecuted_steps(self):
        self.record()
        d=WarehouseBatchDialog([self.item],'technician_sat_external',Mock(),report_folder=self.folder,recovery_only=True)
        self.addCleanup(d.deleteLater)
        d._completed((WarehouseResult(self.item,status='failed',step='Preparación incompleta',completed_steps=1),))
        self.assertNotIn('✓ Confirmar acción',d.steps.text())
        self.assertNotIn('✓ Seleccionar acción',d.steps.text())
        self.assertTrue(d.retry_button.isEnabled())

    def test_result_dialog_retry_opens_review_without_submitting(self):
        self.record()
        d=WarehouseBatchDialog([self.item],'technician_sat_external',Mock(),report_folder=self.folder,recovery_only=True)
        self.addCleanup(d.deleteLater)
        self.assertTrue(d.retry_button.isEnabled())
        with patch('technician_sat_ui.TechnicianSatDialog') as cls:
            d.start_preparation_retry()
        cls.assert_called_once();cls.return_value.show.assert_called_once()
        cls.return_value.start_operation.assert_not_called()
        self.assertTrue(cls.call_args.kwargs['retry_records'])

class LegacyReferenceReadTests(TestCase):
    def test_reference_is_proposed_only_when_complete_and_unambiguous(self):
        from technician_sat import technician_sat_defaults
        for references,total,expected in ((['stock'],1,'stock'),(['stock','1234'],2,''),(['stock'],5,'')):
            with self.subTest(references=references,total=total):
                session=Mock();session.open.return_value='APPR'
                session.identity.return_value={'Activo':'A','Nº de serie':'S','Planta':'LAB-BAD'}
                session.reader.value.side_effect=['Current fault','0,50']
                with patch('technician_sat.TechnicianSatPreparer') as cls:
                    cls.return_value.worklog_snapshot.return_value={'rows':[
                        {'cells':['CLIENTNOTE','inc: '+reference]} for reference in references], 'totals':[total]}
                    result=technician_sat_defaults([WarehouseItem('1',serial='S')],
                        session_factory=lambda:session,read_reference=True)
                self.assertEqual(result['1']['incident'],expected)
                session.driver.find_element.assert_not_called();session.close.assert_called_once()
