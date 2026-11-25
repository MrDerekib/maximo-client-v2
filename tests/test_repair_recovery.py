"""Failure injection for technician completion. No real browser, account or OT."""
import tests
import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication, QMessageBox
from warehouse import WarehouseItem, WarehouseResult
from warehouse_recovery import RecoveryStore, repair_retry_allowed, PendingOperationError
from failure_catalog import default_selection
from technician_repair import reviewed_repair, run_repair
from technician_repair_ui import RepairDialog, RepairProgressDialog
from tests.test_support import temporary_directory

IDENTITY={'Activo':'A','Nº de serie':'S','Planta':'LAB-BAD'}


def plan(action='close'):
    return reviewed_repair(WarehouseItem('1',serial='S'),{
        'reference':'inc: stock','entries':[{'summary':'Test ok','details':'Comprobado'}],
        'duration':'0,5','time_mode':'end','time':(datetime.now()-timedelta(minutes=5)).isoformat(timespec='seconds'),
        'action':action,'justification':'Irreparable','print_report':True},default_selection())


def session(state='INPRG',history=0):
    s=Mock();s.open.return_value=state;s.identity.return_value=dict(IDENTITY)
    s.history_count.return_value=history;s.verify.return_value=state
    return s


class RepairRecoveryTests(TestCase):
    def test_timeout_then_late_issue_is_verified_without_second_confirmation(self):
        for action,expected in (('close','ISSUE'),('discard','CLOSE')):
            with self.subTest(action=action), temporary_directory() as folder:
                p=plan(action);store=RecoveryStore(Path(folder));initial=session()
                first=session('INPRG');late=session(expected,1)
                factory=Mock(side_effect=[initial,first,late]);events=[]
                with patch('technician_repair.RepairPreparer'),patch('technician_repair.RepairCloser') as closer,patch('technician_repair.verify_saved_repair') as checked:
                    def uncertain(*args):
                        mark=closer.call_args.args[2]
                        mark('route_attempted',route_attempted=True,final_route_attempted=True)
                        mark('confirmation_attempted',confirmation_attempted=True)
                        raise TimeoutError('Respuesta perdida')
                    closer.return_value.run_close.side_effect=uncertain
                    with self.assertLogs(level='ERROR'):
                        result=run_repair(p,store=store,session_factory=factory,journal=events.append)
                    self.assertEqual(result['status'],expected)
                    self.assertTrue(result['recovered_after_error'])
                    self.assertEqual(store.get('1')['phase'],'verified')
                    self.assertTrue(any(e['event']=='repair_auto_recheck' for e in events))
                    checked.assert_called_once_with(late,json.loads(json.dumps(asdict(p))))
                    closer.return_value.run_close.assert_called_once()
                    for read in (first,late):read.accept_button.assert_not_called();read.route.assert_not_called();read.close.assert_called_once()
                    initial.close.assert_called_once()

    def test_final_state_without_history_or_dates_is_not_success_or_retryable(self):
        for missing in ('history','dates','identity'):
            with self.subTest(missing=missing),temporary_directory() as folder:
                store=RecoveryStore(Path(folder));initial=session();read=session('ISSUE',1)
                if missing=='history':read.history_count.return_value=0
                if missing=='identity':read.identity.return_value=dict(IDENTITY,Activo='OTHER')
                with patch('technician_repair.RepairPreparer'),patch('technician_repair.RepairCloser') as closer,patch('technician_repair.verify_saved_repair') as checked:
                    if missing=='dates':checked.side_effect=RuntimeError('Las fechas no coinciden')
                    def fail(*args):
                        closer.call_args.args[2]('confirmation_attempted',confirmation_attempted=True)
                        raise TimeoutError('Respuesta perdida')
                    closer.return_value.run_close.side_effect=fail
                    with self.assertLogs(level='ERROR'), self.assertRaises(TimeoutError):
                        run_repair(plan(),store=store,session_factory=Mock(side_effect=[initial,read,read]))
                    record=store.get('1')
                    self.assertNotEqual(record['phase'],'verified')
                    self.assertFalse(repair_retry_allowed(record))
                    closer.return_value.run_close.assert_called_once()

    def test_reviewed_retry_resumes_preparation_with_same_operation_and_no_second_start(self):
        with temporary_directory() as folder:
            p=plan();store=RecoveryStore(Path(folder))
            record=store.begin(p.item,'technician_close',IDENTITY,'APPR',preparing=True,reviewed_request=asdict(p))
            record=store.update(record,'route_attempted',route_attempted=True,start_attempted=True,final_route_attempted=False)
            self.assertTrue(repair_retry_allowed(record))
            s=session();s.history_count.side_effect=[0,1]
            with patch('technician_repair.RepairPreparer') as preparer,patch('technician_repair.RepairCloser') as closer,patch('technician_repair.verify_repair_entries'):
                closer.return_value.run_close.return_value={'status':'ISSUE','ot':'1'}
                result=run_repair(p,store=store,session_factory=lambda:s,retry_record=record)
            self.assertEqual(result['operation_id'],record['operation_id'])
            self.assertEqual(store.get('1')['retry_count'],1)
            preparer.return_value.run.assert_not_called()

    def test_old_ambiguous_or_concurrent_record_cannot_resume_before_browser_open(self):
        for flag in ('confirmation_attempted','final_route_attempted','legacy','changed_operation'):
            with self.subTest(flag=flag),temporary_directory() as folder:
                p=plan();store=RecoveryStore(Path(folder))
                record=store.begin(p.item,'technician_close',IDENTITY,'INPRG',preparing=True,reviewed_request=asdict(p))
                supplied=dict(record)
                if flag=='legacy':record=store.update(record,'route_attempted',route_attempted=True)
                elif flag=='changed_operation':supplied['operation_id']='wrong'
                else:record=store.update(record,'route_attempted',route_attempted=True,**{flag:True})
                if flag!='changed_operation':supplied=record
                factory=Mock()
                with self.assertLogs(level='ERROR'),self.assertRaises(RuntimeError):
                    run_repair(p,store=store,session_factory=factory,retry_record=supplied)
                factory.assert_not_called()

    def test_uncertain_start_is_not_replayed_if_fresh_read_still_says_appr(self):
        with temporary_directory() as folder:
            p=plan();store=RecoveryStore(Path(folder))
            record=store.begin(p.item,'technician_close',IDENTITY,'APPR',preparing=True,reviewed_request=asdict(p))
            record=store.update(record,'route_attempted',start_attempted=True,route_attempted=True,final_route_attempted=False)
            with patch('technician_repair.RepairPreparer') as prepare:
                with self.assertLogs(level='ERROR'),self.assertRaisesRegex(RuntimeError,'inicio anterior'):
                    run_repair(p,store=store,session_factory=lambda:session('APPR'),retry_record=record)
                prepare.assert_not_called()

    def test_atomic_retry_gate_rejects_changed_identity_action_and_confirmation(self):
        with temporary_directory() as folder:
            p=plan();store=RecoveryStore(Path(folder))
            record=store.begin(p.item,'technician_close',IDENTITY,'INPRG',preparing=True,reviewed_request=asdict(p))
            changed=asdict(p);changed['action']='discard'
            with self.assertRaises(PendingOperationError):store.resume_repair_preparation(record,changed)
            store.update(record,'confirmation_attempted',confirmation_attempted=True)
            with self.assertRaises(PendingOperationError):store.resume_repair_preparation(record,asdict(p))


class RepairRecoveryUiTests(TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def dialog(self):
        d=RepairDialog(WarehouseItem('1',serial='S'),default_selection(),autoload=False,default_action='close')
        d.preview_ready({'state':'INPRG','fault':'Fallo','duration':'0,5','reference':'inc: stock','entries':[{'summary':'Test ok','details':'Comprobado'}]})
        d.progress_dialog=RepairProgressDialog(d)
        self.addCleanup(d.progress_dialog.deleteLater);self.addCleanup(d.deleteLater)
        return d

    def test_ambiguous_confirmation_only_enables_read_only_recheck_in_same_window(self):
        d=self.dialog();p=plan()
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder));record=store.begin(p.item,'technician_close',IDENTITY,'INPRG',preparing=True,reviewed_request=asdict(p))
            store.update(record,'confirmation_attempted',confirmation_attempted=True)
            with patch('technician_repair_ui.RecoveryStore',return_value=store),patch('technician_repair_ui.RepairRecheckWorker') as worker,patch('technician_repair_ui.RepairWorker') as execute:
                worker.return_value.isRunning.return_value=False
                progress=d.progress_dialog;progress.failure('Timeout');progress.worker_finished()
                self.assertTrue(progress.retry_button.isEnabled())
                progress.retry_button.click()
                self.assertIs(d.progress_dialog,progress)
                worker.return_value.start.assert_called_once();execute.assert_not_called()
                self.assertFalse(progress.close_button.isEnabled());self.assertTrue(progress.stop_button.isEnabled())

    def test_auto_recheck_does_not_paint_an_uncertain_confirmation_green(self):
        d=self.dialog();progress=d.progress_dialog
        progress.set_stage(4,'Confirmando')
        progress.set_stage(5,'Reverificación automática sin volver a confirmar')
        self.assertEqual(progress.table.item(4,1).text(),'Pendiente de verificar')
        self.assertEqual(progress.table.item(5,1).text(),'En curso')
        progress.failure('Resultado pendiente')
        self.assertEqual(progress.table.item(5,1).text(),'Revisar resultado')

    def test_retry_preserves_manual_fields_and_requires_new_confirmation(self):
        d=self.dialog();p=plan()
        d.reference.setText('inc: manual');d.confirm.setChecked(True)
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder));record=store.begin(p.item,'technician_close',IDENTITY,'INPRG',preparing=True,reviewed_request=asdict(p))
            with patch('technician_repair_ui.RecoveryStore',return_value=store),patch('technician_repair_ui.RepairWorker') as execute:
                progress=d.progress_dialog;progress.failure('Preparation failed');progress.worker_finished()
                self.assertTrue(progress.retry_button.isEnabled());progress.review_button.click()
                self.assertEqual(d.reference.text(),'inc: manual')
                self.assertFalse(d.confirm.isChecked());self.assertTrue(d.submit.isEnabled());self.assertFalse(d.action.isEnabled())
                self.assertEqual(d._retry_record['operation_id'],record['operation_id'])
                execute.assert_not_called()

    def test_recheck_success_finishes_pending_record_but_never_automatically_prints(self):
        d=self.dialog();p=plan();printed=[];d.print_requested.connect(printed.append)
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder));record=store.begin(p.item,'technician_close',IDENTITY,'INPRG',verified_status='ISSUE',reviewed_request=asdict(p))
            with patch('technician_repair_ui.RecoveryStore',return_value=store),patch('technician_repair_ui.apply_closed_repair',return_value=True):
                d.recheck_ready(WarehouseResult(p.item,status='success',verified_status='ISSUE',operation_id=record['operation_id']))
                d.progress_dialog.worker_finished()
            self.assertIsNone(store.get('1'));self.assertEqual(printed,[])
            self.assertTrue(d.progress_dialog.print_button.isEnabled())
            self.assertFalse(d.progress_dialog.retry_button.isEnabled())

    def test_local_save_failure_keeps_recheck_and_never_repeats_remote_operation(self):
        d=self.dialog();p=plan()
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder));record=store.begin(p.item,'technician_close',IDENTITY,'INPRG',verified_status='ISSUE',reviewed_request=asdict(p))
            with patch('technician_repair_ui.RecoveryStore',return_value=store),patch('technician_repair_ui.apply_closed_repair',side_effect=OSError('Locked')):
                with self.assertLogs(level='ERROR'):
                    d.recheck_ready(WarehouseResult(p.item,status='success',verified_status='ISSUE',operation_id=record['operation_id']))
                d.progress_dialog.worker_finished()
            self.assertTrue(d.progress_dialog.retry_button.isEnabled())
            self.assertIn('Pendiente de guardar en MD. Pulsa Revisar y reintentar para guardar el resultado.',
                          d.progress_dialog.message.text())
