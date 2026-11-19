import tests
import json
from dataclasses import asdict
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QMessageBox
from tests import test_repair_recovery as fixtures
from tests.test_support import temporary_directory
from warehouse_recovery import RecoveryStore
from technician_repair import inspect_repair_recovery,repair_plan_from_record,run_repair

class StageRecoveryTests(TestCase):
    def record(self,store,started=True):
        p=fixtures.plan();r=store.begin(p.item,'technician_close',fixtures.IDENTITY,'APPR',preparing=True,reviewed_request=asdict(p))
        return store.update(r,'route_attempted' if started else 'preparing',route_attempted=started,start_attempted=started,final_route_attempted=False)
    def test_start_timeout_is_assessed_against_inprg_not_issue_without_writes(self):
        for state,started,kind in [('INPRG',True,'resume'),('APPR',False,'resume'),('APPR',True,'pending'),('ISSUE',True,'verify_final')]:
            with self.subTest(state=state,started=started),temporary_directory() as folder:
                store=RecoveryStore(Path(folder));r=self.record(store,started);s=fixtures.session(state);events=[]
                result=inspect_repair_recovery(r,store=store,session_factory=lambda:s,journal=events.append)
                self.assertEqual(result['kind'],kind);self.assertEqual(result['state'],state)
                self.assertEqual(store.get('1'),r)
                s.route.assert_not_called();s.accept_button.assert_not_called();s.close.assert_called_once()
                self.assertFalse(events[0]['confirmation_replayed'])
    def test_uncertain_final_confirmation_is_never_offered_as_resume(self):
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder));r=self.record(store);r=store.update(r,'confirmation_attempted',confirmation_attempted=True)
            factory=Mock();result=inspect_repair_recovery(r,store=store,session_factory=factory)
            self.assertEqual(result['kind'],'verify_final');factory.assert_not_called()
    def test_changed_identity_or_concurrent_final_route_blocks_continuation(self):
        for changed in ('identity','route'):
            with self.subTest(changed=changed),temporary_directory() as folder:
                store=RecoveryStore(Path(folder));r=self.record(store);s=fixtures.session()
                if changed=='identity':s.identity.return_value=dict(fixtures.IDENTITY,Activo='OTHER')
                else:s.open.side_effect=lambda ot:(store.update(r,'route_attempted',final_route_attempted=True) and 'INPRG')
                with self.assertRaises(RuntimeError):inspect_repair_recovery(r,store=store,session_factory=lambda:s)
                s.close.assert_called_once();s.route.assert_not_called();s.accept_button.assert_not_called()
    def test_saved_plan_is_preserved_and_invalid_dates_are_rejected(self):
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder));r=self.record(store)
            self.assertEqual(json.loads(json.dumps(asdict(repair_plan_from_record(r)))),r['reviewed_request'])
            r['reviewed_request']['end']='2000-01-01T00:00:00'
            with self.assertRaises(RuntimeError):repair_plan_from_record(r)
    def test_changed_state_after_user_confirmation_stops_before_any_preparation(self):
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder));r=self.record(store,False);p=repair_plan_from_record(r)
            with patch('technician_repair.RepairPreparer') as preparer,self.assertLogs(level='ERROR'),self.assertRaisesRegex(RuntimeError,'cambió de estado'):
                run_repair(p,store=store,session_factory=lambda:fixtures.session('APPR'),retry_record={**r,'resume_state':'INPRG'})
            preparer.assert_not_called()

class ContinuationUiTests(TestCase):
    setUpClass=classmethod(fixtures.RepairRecoveryUiTests.setUpClass.__func__)
    dialog=fixtures.RepairRecoveryUiTests.dialog
    def test_continue_first_reads_and_never_executes_automatically(self):
        d=self.dialog()
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder));p=fixtures.plan();r=store.begin(p.item,'technician_close',fixtures.IDENTITY,'APPR',preparing=True,reviewed_request=asdict(p))
            with patch('technician_repair_ui.RecoveryStore',return_value=store),patch.object(d,'recheck_repair') as check,patch.object(d,'launch') as execute:
                d.continue_repair();check.assert_called_once();execute.assert_not_called()
                d.recheck_ready({'kind':'resume','state':'INPRG','operation_id':r['operation_id'],'detail':'La OT ya está iniciada.'})
                execute.assert_not_called();self.assertEqual(d.progress_dialog.table.item(2,1).text(),'Completado')
                d.progress_dialog.worker_finished();self.assertEqual(d.progress_dialog.retry_button.text(),'Continuar cierre…')
    def test_same_progress_window_only_continues_after_explicit_confirmation(self):
        for answer in (QMessageBox.Yes,QMessageBox.No):
            with self.subTest(answer=answer),temporary_directory() as folder:
                d=self.dialog();progress=d.progress_dialog;store=RecoveryStore(Path(folder));p=fixtures.plan()
                r=store.begin(p.item,'technician_close',fixtures.IDENTITY,'APPR',preparing=True,reviewed_request=asdict(p))
                d._resume_assessment={'kind':'resume','state':'INPRG','operation_id':r['operation_id'],'detail':'No se iniciará otra vez.'}
                with patch('technician_repair_ui.RecoveryStore',return_value=store),patch('technician_repair_ui.QMessageBox.question',return_value=answer) as confirm,patch.object(d,'launch') as execute:
                    d.continue_repair();confirm.assert_called_once()
                    self.assertIn('INPRG',confirm.call_args.args[2]);self.assertIs(d.progress_dialog,progress)
                    if answer==QMessageBox.Yes:
                        execute.assert_called_once();self.assertEqual(asdict(execute.call_args.args[0]),r['reviewed_request'])
                        self.assertEqual(d._retry_record['resume_state'],'INPRG')
                    else:execute.assert_not_called()
