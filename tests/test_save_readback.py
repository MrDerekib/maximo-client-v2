"""Guarded recovery for missing Save notices, without repeating writes."""
import tests
from unittest import TestCase
from unittest.mock import Mock
from workorder_start import WorkorderStarter, SaveConfirmationMissing
from technician_sat import TechnicianSatPreparer, reviewed_sat_plans
from warehouse import WarehouseItem
from failure_catalog import default_selection, resolve_selection


class SaveReadbackTests(TestCase):
    def reader(self):
        p=WorkorderStarter(Mock(), '1')
        for method in ('idle','check_startable','reject_dialogs','check_location','tab',
                       'reload_workorder','set_anomaly_diagnostic_stage'):
            setattr(p,method,Mock())
        p.save=Mock(side_effect=SaveConfirmationMissing('notice absent'))
        p.value=Mock(return_value='RFN-70')
        path=resolve_selection(default_selection())['path']
        p.failure_rows=Mock(return_value=[{'type':r['type'],'code':r['code']} for r in path])
        p.solution_codes=Mock(return_value={r['type']:r['code'] for r in path})
        p.wait=Mock(side_effect=lambda predicate,label:predicate(None))
        return p,path

    def test_missing_notice_is_accepted_only_after_complete_fresh_readback(self):
        p,path=self.reader()
        self.assertTrue(p.save_anomalies(path,'RFN-70'))
        p.save.assert_called_once();p.reload_workorder.assert_called_once()
        p.driver.find_element.assert_not_called()

    def test_mismatched_class_codes_or_solutions_never_pass(self):
        for kind in ('class','codes','solutions','pending_deletion'):
            with self.subTest(kind=kind):
                p,path=self.reader()
                if kind=='class':p.value.return_value='OTHER'
                elif kind=='codes':p.failure_rows.return_value=[]
                elif kind=='solutions':p.solution_codes.return_value={}
                else:p.failure_rows.return_value[0]['toggleTitle']='Deshacer suprimir'
                self.assertFalse(p.save_anomalies(path,'RFN-70'))
                p.save.assert_called_once();p.reload_workorder.assert_called_once()

    def test_explicit_error_or_timeout_does_not_use_missing_notice_recovery(self):
        for error in (RuntimeError('BMXAA4214E'),TimeoutError('response missing')):
            with self.subTest(error=type(error).__name__):
                p,path=self.reader();p.save.side_effect=error
                with self.assertRaises(type(error)):p.save_anomalies(path,'RFN-70')
                p.reload_workorder.assert_not_called()

    def test_failed_readback_stops_without_a_second_save(self):
        p,path=self.reader();p.reload_workorder.side_effect=TimeoutError('record unavailable')
        with self.assertRaises(TimeoutError):p.save_anomalies(path,'RFN-70')
        p.save.assert_called_once()

    def save_notice_reader(self,alerts):
        p=WorkorderStarter(Mock(),'1')
        p.idle=Mock();p.check_startable=Mock();p.reject_dialogs=Mock()
        p.save_action_state=Mock(return_value={'control':Mock(),'unavailable':None})
        p.click_fresh=Mock();p.response_sequence=Mock(side_effect=[0,1])
        p.dialog_snapshot=Mock(return_value=[])
        p.wait=Mock(side_effect=lambda predicate,label:predicate(None))
        p.driver.execute_script.return_value=alerts
        return p

    def test_explicit_error_alert_wins_over_a_visible_success_notice(self):
        p=self.save_notice_reader(['BMXAA4205I saved','BMXAA4214E rejected'])
        with self.assertRaisesRegex(RuntimeError,'BMXAA4214E') as caught:p.save()
        self.assertNotIsInstance(caught.exception,SaveConfirmationMissing)
        p.click_fresh.assert_called_once()

    def test_absent_success_notice_is_distinguished_from_rejection(self):
        p=self.save_notice_reader([])
        with self.assertRaises(SaveConfirmationMissing):p.save()
        p.click_fresh.assert_called_once()

    def prepared_reader(self):
        p=TechnicianSatPreparer(Mock(),'1')
        for method in ('require_approved','apply_anomalies','set_repair_duration',
                       'ensure_incident','reload_workorder','verify_prepared','wait'):
            setattr(p,method,Mock())
        p.fault_reason=Mock(return_value='Fault')
        p.save=Mock(side_effect=SaveConfirmationMissing('notice absent'))
        plan,=reviewed_sat_plans([WarehouseItem('1')],
            {'1':{'duration':'0,50','incident':'stock','reason':'Fault'}},default_selection())
        return p,plan

    def test_final_preparation_missing_notice_requires_fresh_full_verification(self):
        p,plan=self.prepared_reader()
        self.assertTrue(p.prepare(plan)['prepared'])
        p.save.assert_called_once();p.reload_workorder.assert_called_once()
        p.verify_prepared.assert_called_once_with(plan)
        p.driver.find_element.assert_not_called()

    def test_final_preparation_mismatch_stops_before_route(self):
        p,plan=self.prepared_reader()
        p.verify_prepared.side_effect=RuntimeError('Hours not saved')
        with self.assertRaisesRegex(RuntimeError,'Hours not saved'):p.prepare(plan)
        p.save.assert_called_once();p.driver.find_element.assert_not_called()

    def test_final_preparation_real_error_is_not_ignored(self):
        p,plan=self.prepared_reader();p.save.side_effect=RuntimeError('BMXAA4214E')
        with self.assertRaisesRegex(RuntimeError,'BMXAA4214E'):p.prepare(plan)
        p.reload_workorder.assert_not_called();p.verify_prepared.assert_not_called()
