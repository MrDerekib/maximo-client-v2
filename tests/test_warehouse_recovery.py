"""Failure injection against an in-memory server; no real browser or Maximo calls."""
import tests
from pathlib import Path
from collections import Counter
from threading import Event
from unittest import TestCase
from unittest.mock import Mock, patch

from tests.test_support import temporary_directory
from warehouse import WarehouseItem
from warehouse_recovery import RecoveryStore
from warehouse_transport import run_live, reverify_pending, FINAL_STATES


class FakeServer:
    def __init__(self, action='dispatch', states=None):
        self.action=action;self.states=states or {'1':'ISSUE'}
        self.sessions=[];self.sent=Counter();self.routed=Counter();self.details_sent=Counter()
        self.history=Counter();self.lost=set();self.crash=set();self.reject=set();self.identity_changed=set()
        self.route_failure=set();self.open_failures=0;self.events=[];self.lost_details=set();self.lost_sat=set()

    def session(self):
        session=Mock();self.sessions.append(session);current={'ot':None}
        def opened(ot):
            current['ot']=ot;self.events.append(('read',ot))
            if self.open_failures:
                self.open_failures-=1;raise TimeoutError('Temporary connection loss')
            return self.states[ot]
        def identity():
            ot=current['ot']
            return {'Activo':('CHANGED' if ot in self.identity_changed else 'ASSET-'+ot),
                    'Nº de serie':'SERIAL-'+ot,'Planta':'LAB-BAD'}
        def route():
            ot=current['ot'];self.routed[ot]+=1
            if ot in self.route_failure:raise TimeoutError('Route response lost')
        def element(by,identifier):
            assert identifier=='ROUTEWF_WO-MAIN_-tbb_image'
            return Mock(click=Mock(side_effect=route))
        def accepted():
            ot=current['ot'];self.sent[ot]+=1;self.events.append(('sent',ot))
            if ot in self.reject:raise RuntimeError('BMXAA9999E rejection')
            if self.action.startswith('receive_sat'):
                if ot in self.lost_sat:raise TimeoutError('Lost before SAT details')
                return
            self.states[ot]=FINAL_STATES[self.action]
            if ot in self.crash:raise SystemExit('Simulated process crash after submission')
            if ot in self.lost:raise TimeoutError('Lost response after successful submission')
        def verified(ot,state,expected_identity):
            if self.states[ot]!=state or identity()!=expected_identity:raise RuntimeError('Verification mismatch')
            return state
        def details(action,text,initial,expected_identity,before_accept):
            before_accept();ot=current['ot'];self.details_sent[ot]+=1
            self.history[ot]+=1;self.states[ot]='ISSUE'
            if ot in self.lost_details:raise TimeoutError('Lost after SAT details OK')
        session.open.side_effect=opened;session.identity.side_effect=identity
        session.driver.find_element.side_effect=element
        session.choice.return_value={'id':'option','checked':True}
        session.accept_button.return_value.click.side_effect=accepted
        session.verify.side_effect=verified
        session.history_count.side_effect=lambda caption:self.history[current['ot']]
        session.sat_details.side_effect=details
        return session


class RecoveryTests(TestCase):
    def setUp(self):
        temp=temporary_directory();self.folder=Path(temp.__enter__());self.addCleanup(temp.__exit__,None,None,None)
        self.store=RecoveryStore(self.folder)

    def run_batch(self,server,items=None,**kwargs):
        return run_live(items or [WarehouseItem(ot,serial='SERIAL-'+ot) for ot in server.states],server.action,
                        session_factory=server.session,recovery_store=self.store,**kwargs)

    def test_middle_timeout_is_rechecked_only_after_all_eighteen_finish(self):
        server=FakeServer(states={str(i):'ISSUE' for i in range(1,19)});server.lost.add('7')
        entries=[];results=self.run_batch(server,journal=entries.append)
        self.assertEqual([r.status for r in results],['success']*18)
        self.assertEqual(server.sent,Counter({str(i):1 for i in range(1,19)}))
        self.assertEqual(server.routed,server.sent)
        self.assertLess(max(i for i,e in enumerate(entries) if e.get('event')=='ot_started'),
                        min(i for i,e in enumerate(entries) if e.get('event')=='recheck_started'))
        self.assertEqual(server.events[-1],('read','7'))
        recovery_session=server.sessions[-1]
        recovery_session.driver.find_element.assert_not_called();recovery_session.accept_button.assert_not_called()

    def test_read_failure_before_route_can_retry_once(self):
        server=FakeServer();server.open_failures=1
        result=self.run_batch(server)[0]
        self.assertEqual(result.status,'success');self.assertEqual(server.sent['1'],1)
        self.assertEqual(len(server.sessions),2);server.sessions[0].close.assert_called_once()

    def test_two_failed_reads_stop_before_any_effect(self):
        server=FakeServer();server.open_failures=3
        result=self.run_batch(server)[0]
        self.assertEqual(result.status,'failed');self.assertEqual(len(server.sessions),2)
        self.assertFalse(server.routed);self.assertFalse(server.sent);self.assertFalse(self.store.pending())

    def test_route_failure_never_replays_route_or_accept(self):
        server=FakeServer();server.route_failure.add('1')
        result=self.run_batch(server)[0]
        self.assertEqual(result.status,'uncertain');self.assertEqual(server.routed['1'],1)
        self.assertFalse(server.sent);self.assertEqual(len(self.store.pending()),1)
        self.assertEqual(self.store.pending()[0]['phase'],'route_attempted')

    def test_failed_persistence_prevents_routing(self):
        server=FakeServer()
        with patch.object(self.store,'begin',side_effect=OSError('Disk failure')):
            result=self.run_batch(server)[0]
        self.assertEqual(result.status,'failed');self.assertFalse(server.routed);self.assertFalse(server.sent)

    def test_persisted_confirmation_marker_exists_before_click(self):
        server=FakeServer();original=server.session
        def factory():
            session=original();accepted=session.accept_button.return_value.click.side_effect
            def check():
                record=self.store.get('1')
                self.assertTrue(record['confirmation_attempted']);self.assertEqual(record['phase'],'confirmation_attempted')
                return accepted()
            session.accept_button.return_value.click.side_effect=check
            return session
        result=run_live([WarehouseItem('1')],'dispatch',session_factory=factory,recovery_store=self.store)
        self.assertEqual(result[0].status,'success')

    def test_rejected_confirmation_stays_uncertain_and_does_not_retry(self):
        server=FakeServer();server.reject.add('1')
        result=self.run_batch(server)[0]
        self.assertEqual(result.status,'uncertain');self.assertEqual(server.sent['1'],1)
        self.assertEqual(server.routed['1'],1);self.assertTrue(self.store.pending())

    def test_pending_operation_blocks_a_second_batch_even_with_another_action(self):
        server=FakeServer();server.reject.add('1');self.run_batch(server)
        factory=Mock(side_effect=AssertionError('No browser should be opened'))
        result=run_live([WarehouseItem('1')],'receive',session_factory=factory,recovery_store=self.store)
        self.assertEqual(result[0].status,'uncertain');factory.assert_not_called()

    def test_process_crash_can_recover_with_fresh_store_and_zero_resubmissions(self):
        server=FakeServer();server.crash.add('1')
        with self.assertRaises(SystemExit):self.run_batch(server)
        restored=RecoveryStore(self.folder)
        records=restored.pending();self.assertEqual(len(records),1)
        self.assertEqual(records[0]['phase'],'confirmation_attempted')
        result=reverify_pending(records,recovery_store=restored,session_factory=server.session)
        self.assertEqual(result[0].status,'success');self.assertEqual(server.sent['1'],1)
        server.sessions[-1].driver.find_element.assert_not_called()
        self.assertEqual(restored.get('1')['phase'],'verified')

    def test_still_initial_state_remains_pending_and_recheck_is_read_only(self):
        server=FakeServer();server.reject.add('1');self.run_batch(server,auto_recheck=False)
        previous=len(server.sessions)
        result=reverify_pending(self.store.pending(),recovery_store=self.store,session_factory=server.session)
        self.assertEqual(result[0].status,'uncertain');self.assertEqual(server.sent['1'],1)
        for session in server.sessions[previous:]:
            session.driver.find_element.assert_not_called();session.accept_button.assert_not_called()

    def test_changed_identity_cannot_be_verified(self):
        server=FakeServer();server.lost.add('1');self.run_batch(server,auto_recheck=False)
        server.identity_changed.add('1')
        result=reverify_pending(self.store.pending(),recovery_store=self.store,session_factory=server.session)
        self.assertEqual(result[0].status,'uncertain');self.assertEqual(server.sent['1'],1)
        self.assertIn('identidad',result[0].detail)

    def test_already_closed_is_not_executed_again(self):
        server=FakeServer(states={'1':'CLOSE'})
        result=self.run_batch(server)[0]
        self.assertEqual(result.status,'already_done');self.assertEqual(result.verified_status,'CLOSE')
        self.assertFalse(server.routed);self.assertFalse(server.sent)

    def test_stop_does_not_start_second_pass_or_next_ot(self):
        server=FakeServer(states={'1':'ISSUE','2':'ISSUE'});server.lost.add('1');stop=Event()
        def progress(index,result):
            if result.status=='uncertain':stop.set()
        results=self.run_batch(server,stop=stop,progress=progress)
        self.assertEqual([r.status for r in results],['uncertain','stopped'])
        self.assertEqual(len(server.sessions),1);self.assertEqual(server.sent['1'],1)

    def test_sat_details_timeout_recovers_only_when_matching_history_advanced(self):
        server=FakeServer(action='receive_sat_external',states={'1':'WAPPR'});server.lost_details.add('1')
        result=self.run_batch(server,details={'1':'PRIVATE NOTE'})[0]
        self.assertEqual(result.status,'success');self.assertEqual(server.sent['1'],1)
        self.assertEqual(server.details_sent['1'],1)
        self.assertNotIn('PRIVATE NOTE',next(self.store.folder.glob('*.json')).read_text(encoding='utf-8'))
        server.sessions[-1].sat_details.assert_not_called()

    def test_sat_lost_before_details_does_not_complete_them_during_recheck(self):
        server=FakeServer(action='receive_sat_internal',states={'1':'WAPPR'});server.lost_sat.add('1')
        result=self.run_batch(server)[0]
        self.assertEqual(result.status,'uncertain');self.assertFalse(server.details_sent)
        self.assertEqual(server.sent['1'],1);self.assertFalse(self.store.get('1')['details_attempted'])

    def test_sat_issue_without_new_history_is_not_enough(self):
        server=FakeServer(action='receive_sat_external',states={'1':'WAPPR'});server.lost_sat.add('1')
        self.run_batch(server,auto_recheck=False);server.states['1']='ISSUE'
        result=reverify_pending(self.store.pending(),recovery_store=self.store,session_factory=server.session)
        self.assertEqual(result[0].status,'uncertain');self.assertEqual(server.sent['1'],1)

    def test_verified_remote_result_retries_only_local_write(self):
        server=FakeServer();self.run_batch(server)
        from warehouse_ui import WarehouseThread
        from warehouse_transport import reverify_pending as real_reverify
        worker=WarehouseThread([WarehouseItem('1')],'dispatch',self.folder/'recheck-events.jsonl',recoveries=self.store.pending())
        finished=[];worker.completed.connect(finished.append)
        forbidden=Mock(side_effect=AssertionError('Local recovery must not open a browser'))
        def recheck(records,**kwargs):return real_reverify(records,session_factory=forbidden,**kwargs)
        with patch('warehouse_transport.reverify_pending',side_effect=recheck), \
             patch('db.apply_warehouse_status',side_effect=[OSError('Locked'),True]) as save:
            worker.run()
        self.assertEqual(save.call_count,2);forbidden.assert_not_called()
        self.assertTrue(finished[0][0].local_status_saved);self.assertFalse(self.store.pending())
        self.assertEqual(server.sent['1'],1)

    def test_corrupt_pending_record_blocks_new_execution(self):
        server=FakeServer();server.reject.add('1');self.run_batch(server,auto_recheck=False)
        next(self.store.folder.glob('*.json')).write_text('{broken',encoding='utf-8')
        forbidden=Mock(side_effect=AssertionError('Must not open or send'))
        result=run_live([WarehouseItem('1')],'dispatch',recovery_store=self.store,session_factory=forbidden)
        self.assertEqual(result[0].status,'failed');forbidden.assert_not_called()

    def test_failed_initial_fsync_leaves_no_claim_and_sends_nothing(self):
        server=FakeServer()
        with patch('warehouse_recovery.os.fsync',side_effect=OSError('Cannot flush')):
            result=self.run_batch(server)[0]
        self.assertEqual(result.status,'failed');self.assertFalse(server.routed)
        self.assertFalse(self.store.pending())

    def test_recovery_updates_original_report_after_local_sync(self):
        import json
        from dataclasses import asdict
        from warehouse import WarehouseResult
        from warehouse_ui import WarehouseThread
        item=WarehouseItem('1',serial='SERIAL-1')
        store=RecoveryStore(self.folder,origin_report='original-result.json')
        record=store.begin(item,'dispatch',{'Activo':'ASSET-1','Nº de serie':'SERIAL-1','Planta':'LAB-BAD'},'ISSUE',verified_status='CLOSE')
        (self.folder/'original-result.json').write_text(json.dumps({'action':'dispatch','results':[asdict(WarehouseResult(item,status='uncertain'))]}),encoding='utf-8')
        worker=WarehouseThread([item],'dispatch',self.folder/'recovered-events.jsonl',recoveries=[record])
        with patch('db.apply_warehouse_status',return_value=True):worker.run()
        saved=json.loads((self.folder/'original-result.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['results'][0]['status'],'success')
        self.assertTrue(saved['results'][0]['local_status_saved']);self.assertFalse(store.pending())

    def test_persistent_local_failure_keeps_verified_record_for_restart(self):
        server=FakeServer();self.run_batch(server)
        from warehouse_ui import WarehouseThread
        worker=WarehouseThread([WarehouseItem('1')],'dispatch',self.folder/'recheck-events.jsonl',recoveries=self.store.pending())
        finished=[];worker.completed.connect(finished.append)
        with patch('db.apply_warehouse_status',side_effect=OSError('Still locked')):worker.run()
        self.assertEqual(finished[0][0].status,'success');self.assertFalse(finished[0][0].local_status_saved)
        self.assertEqual(RecoveryStore(self.folder).pending()[0]['phase'],'verified')
        self.assertEqual(server.sent['1'],1)

    def test_false_verification_value_cannot_corrupt_persisted_evidence(self):
        server=FakeServer();original=server.session
        def factory():
            session=original();session.verify.side_effect=None;session.verify.return_value='ISSUE';return session
        result=run_live([WarehouseItem('1')],'dispatch',recovery_store=self.store,session_factory=factory)
        self.assertEqual(result[0].status,'uncertain')
        self.assertEqual(self.store.get('1')['phase'],'confirmation_attempted')

    def test_recovery_cannot_write_report_outside_report_folder(self):
        from warehouse import WarehouseResult
        item=WarehouseItem('1');record=self.store.begin(item,'dispatch',{'Activo':'A','Nº de serie':'S','Planta':'P'},'ISSUE',verified_status='CLOSE')
        record['origin_report']='../outside-result.json'
        with self.assertRaises(RuntimeError):self.store.update_report(record,WarehouseResult(item))

    def test_stale_recovery_record_cannot_apply_an_older_local_state(self):
        server=FakeServer();self.run_batch(server)
        old=self.store.get('1');self.store.complete(old)
        replacement=self.store.begin(WarehouseItem('1'),'receive',old['identity'],'WAPPR')
        forbidden=Mock(side_effect=AssertionError('Stale recovery must not open browser'))
        result=reverify_pending([old],recovery_store=self.store,session_factory=forbidden)[0]
        self.assertEqual(result.status,'uncertain');forbidden.assert_not_called()
        self.assertEqual(self.store.get('1')['operation_id'],replacement['operation_id'])

    def test_recheck_keeps_previous_successful_rows_and_updates_only_pending_row(self):
        from warehouse import WarehouseResult
        from warehouse_ui import WarehouseThread
        first=WarehouseItem('1');second=WarehouseItem('2')
        record=self.store.begin(second,'dispatch',{'Activo':'A2','Nº de serie':'S2','Planta':'P'},'ISSUE',verified_status='CLOSE')
        previous=WarehouseResult(first,status='success',verified_status='CLOSE',local_status_saved=True)
        worker=WarehouseThread([first,second],'dispatch',self.folder/'again-events.jsonl',
            recoveries=[record],previous_results=[previous,WarehouseResult(second,status='uncertain')])
        finished=[];worker.completed.connect(finished.append)
        with patch('db.apply_warehouse_status',return_value=True) as save:worker.run()
        self.assertEqual(finished[0][0],previous)
        self.assertEqual(finished[0][1].status,'success');save.assert_called_once_with('2','CLOSE')

    def test_recovery_dialog_opens_for_review_and_launches_only_read_only_worker(self):
        from PySide6.QtWidgets import QApplication
        from warehouse_ui import WarehouseBatchDialog
        app=QApplication.instance() or QApplication([])
        item=WarehouseItem('1')
        self.store.begin(item,'dispatch',{'Activo':'A','Nº de serie':'S','Planta':'P'},'ISSUE')
        dialog=WarehouseBatchDialog([item],'dispatch',Mock(),report_folder=self.folder,recovery_only=True)
        try:
            self.assertIsNone(dialog._worker);self.assertFalse(dialog._has_started)
            with patch.object(dialog,'_launch_worker') as launch, patch('warehouse_ui.QMessageBox.question') as question:
                dialog.start_operation()
            question.assert_not_called()
            self.assertEqual(launch.call_args.args[0][0]['item']['ot'],'1')
        finally:
            dialog.deleteLater();app.processEvents()

    def test_uncertain_batch_enables_manual_recheck_and_persists_report(self):
        from PySide6.QtWidgets import QApplication
        from warehouse_ui import WarehouseBatchDialog
        from warehouse import WarehouseResult
        app=QApplication.instance() or QApplication([])
        item=WarehouseItem('1')
        self.store.begin(item,'dispatch',{'Activo':'A','Nº de serie':'S','Planta':'P'},'ISSUE')
        dialog=WarehouseBatchDialog([item],'dispatch',Mock(),report_folder=self.folder)
        try:
            dialog._completed([WarehouseResult(item,status='uncertain')])
            self.assertTrue(dialog.recheck_button.isEnabled());self.assertTrue(dialog.report_path.exists())
        finally:
            dialog.deleteLater();app.processEvents()
