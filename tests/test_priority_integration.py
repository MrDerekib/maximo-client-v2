import tests  # Isolate application data before importing product modules.
import threading
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMainWindow,QStatusBar,QLabel
from ui_qt import MaximoDesktopWindow, show_activity_dialog
from priority_notices import PriorityNotices
from task_priorities import Coordinator, JobCounter, scheduled, HIGH, AUTOMATIC
import updater


class Harness(QMainWindow):
    close_progress=Signal(str)
    close_finished=Signal()

    def __init__(self,c):
        super().__init__()
        self.pool=QThreadPool(self)
        self._running_tasks=set();self._coordinated_threads=set()
        self._tasks_idle=threading.Event();self._tasks_idle.set()
        self._closing=False;self.ot_sessions=[]
        self.errors=[]
        self.update_lock=JobCounter();self.reconcile_lock=JobCounter();self.fault_description_lock=JobCounter()
        self.status=QStatusBar(self)
        self.notices=PriorityNotices(lambda text:show_activity_dialog(text,self),self.status.showMessage,self)
        self.destroyed.connect(c.subscribe(self.notices.event_received.emit))

    def start(self,*args,**kwargs):
        if len(args)<3 and 'failed' not in kwargs:
            kwargs['failed']=self.errors.append
        MaximoDesktopWindow._start_task(self,*args,**kwargs)


class IntegrationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def wait_for(self,predicate):
        for _ in range(300):
            if predicate():return
            QTest.qWait(10)
        self.fail('Qt/coordinator did not finish')

    def test_qt_notice_pause_user_and_resume_without_real_maximo(self):
        c=Coordinator();h=Harness(c);entered=threading.Event();release=threading.Event();events=[];completed=[]
        @scheduled('Conciliación',AUTOMATIC)
        def background():
            c.checkpoint('Conciliación','123',0,2)
            entered.set();release.wait(3);events.append('saved')
            c.checkpoint('Conciliación','456',1,2,on_pause=lambda:events.append('retired'))
            events.append('resumed')
        @scheduled('Confirmar recepción',HIGH)
        def user():events.append('user')
        try:
            with patch('task_priorities.coordinator',c):
                h.start(background,lambda _:completed.append('background'),coordinated=True)
                self.wait_for(entered.is_set)
                h.start(user,lambda _:completed.append('user'),coordinated=True)
                self.wait_for(lambda:bool(h.notices.dialogs))
                notice=next(iter(h.notices.dialogs.values()))
                self.assertTrue(notice.isVisible())
                self.assertIn('123',notice.findChild(QLabel,'activityMessage').text())
                self.assertEqual(events,[])
                release.set()
                self.wait_for(lambda:len(completed)==2 and not h._coordinated_threads)
            self.assertEqual(events,['saved','retired','user','resumed'])
            self.assertFalse(h.notices.dialogs)
            self.assertTrue(h._tasks_idle.is_set())
            self.assertEqual(h.errors,[])
        finally:
            release.set();self.wait_for(lambda:not h._coordinated_threads)
            h.notices.close();h.deleteLater();self.app.processEvents()

    def test_coordinated_request_does_not_starve_behind_full_independent_pool(self):
        c=Coordinator();h=Harness(c);h.pool.setMaxThreadCount(1)
        entered=threading.Event();release=threading.Event();completed=[]
        def independent():entered.set();release.wait(3)
        @scheduled('Usuario',HIGH)
        def user():return 'ready'
        try:
            with patch('task_priorities.coordinator',c):
                h.start(independent,lambda _:completed.append('independent'))
                self.wait_for(entered.is_set)
                h.start(user,lambda _:completed.append('user'),coordinated=True)
                self.wait_for(lambda:'user' in completed)
                self.assertNotIn('independent',completed)
                self.assertEqual(h.errors,[])
                release.set();self.wait_for(lambda:not h._running_tasks and not h._coordinated_threads)
        finally:
            release.set();self.wait_for(lambda:not h._running_tasks and not h._coordinated_threads)
            h.notices.close();h.deleteLater();self.app.processEvents()

    def test_close_worker_waits_for_owned_qthreads_and_active_confirmation(self):
        c=Coordinator();h=Harness(c);entered=threading.Event();release=threading.Event();verified=[];closed=[]
        @scheduled('Confirmación',HIGH)
        def user():entered.set();release.wait(3);verified.append(True)
        try:
            with patch('task_priorities.coordinator',c):
                h.start(user,lambda _:None,coordinated=True)
                self.wait_for(entered.is_set)
                h._closing=True;c.shutdown()
                h.close_finished.connect(lambda:closed.append(True))
                closer=threading.Thread(target=lambda:MaximoDesktopWindow._close_worker(h),daemon=True)
                closer.start();QTest.qWait(50)
                self.assertEqual(closed,[])
                release.set();self.wait_for(lambda:bool(closed))
                closer.join(2)
            self.assertEqual(verified,[True])
            self.wait_for(lambda:not h._coordinated_threads)
        finally:
            release.set();self.wait_for(lambda:not h._coordinated_threads)
            h.notices.close();h.deleteLater();self.app.processEvents()

    def test_update_discards_pre_yield_export_and_only_imports_fresh_download(self):
        with tempfile.TemporaryDirectory() as folder:
            old=Path(folder)/'old.xls';old.write_text('old')
            fresh=Path(folder)/'new.xls';fresh.write_text('fresh')
            with patch.object(updater,'load_config',return_value=Mock(download_dir=folder)), \
                 patch.object(updater,'_download_export_once',side_effect=[str(old),str(fresh)]) as download, \
                 patch.object(updater.coordinator,'checkpoint',side_effect=[False,True,False,False,False]), \
                 patch.object(updater,'process_html_table',return_value='fresh_data') as parse, \
                 patch.object(updater,'update_database_from_df',return_value=(1,2)) as commit, \
                 patch.object(updater,'cleanup_exports'):
                self.assertEqual(updater.run_update(),(1,2))
            self.assertEqual(download.call_count,2)
            self.assertFalse(old.exists())
            parse.assert_called_once_with(str(fresh));commit.assert_called_once_with('fresh_data')

    def test_reconciliation_retires_only_its_browser_and_resumes_remaining_ot(self):
        c=Coordinator();entered=threading.Event();release=threading.Event();queued=threading.Event()
        browser1,browser2=Mock(),Mock();looked_up=[];errors=[]
        c.subscribe(lambda e:queued.set() if e['kind']=='waiting' and e['priority']==HIGH else None)
        def read(driver,ot):
            looked_up.append(ot)
            if ot=='1':entered.set();release.wait(3)
            return 'CLOSE'
        def reconcile():
            try:updater.reconcile_inactive_tracking()
            except Exception as exc:errors.append(exc)
        @scheduled('Usuario',HIGH)
        def user():
            browser1.quit.assert_called_once()
            self.assertEqual(looked_up,['1'])
        def user_worker():
            try:user()
            except Exception as exc:errors.append(exc)
        with patch('task_priorities.coordinator',c),patch.object(updater,'coordinator',c), \
             patch.object(updater,'inactive_tracking_candidates',return_value=[('1','EN TALLER'),('2','EN TALLER')]), \
             patch.object(updater,'create_edge_profile',side_effect=['profile1','profile2']), \
             patch.object(updater,'setup_driver',side_effect=[browser1,browser2]), \
             patch.object(updater,'login'),patch.object(updater,'open_workorders_app'), \
             patch.object(updater,'read_workorder_status',side_effect=read), \
             patch.object(updater,'apply_reconciled_status',return_value=True) as save, \
             patch.object(updater,'cleanup_edge_profile') as cleanup:
            low=threading.Thread(target=reconcile,daemon=True);high=threading.Thread(target=user_worker,daemon=True)
            try:
                low.start();self.assertTrue(entered.wait(2));high.start();self.assertTrue(queued.wait(2))
                release.set();low.join(3);high.join(3)
                self.assertFalse(low.is_alive());self.assertFalse(high.is_alive())
                self.assertEqual(errors,[])
                self.assertEqual(looked_up,['1','2']);self.assertEqual(save.call_count,2)
                browser1.quit.assert_called_once();browser2.quit.assert_called_once()
                self.assertEqual([c.args[0] for c in cleanup.call_args_list],['profile1','profile2'])
            finally:release.set();low.join(3);high.join(3)

    def test_shutdown_while_reconciliation_is_paused_does_not_reopen_or_close_twice(self):
        from task_priorities import JobCancelled
        c=Coordinator();unit_entered=threading.Event();unit_release=threading.Event()
        queued=threading.Event();user_entered=threading.Event();user_release=threading.Event()
        browser=Mock();errors=[]
        c.subscribe(lambda e:queued.set() if e['kind']=='waiting' and e['priority']==HIGH else None)
        def read(driver,ot):unit_entered.set();unit_release.wait(3);return 'CLOSE'
        def reconcile():
            try:updater.reconcile_inactive_tracking()
            except Exception as exc:errors.append(exc)
        @scheduled('Usuario',HIGH)
        def user():user_entered.set();user_release.wait(3)
        with patch('task_priorities.coordinator',c),patch.object(updater,'coordinator',c), \
             patch.object(updater,'inactive_tracking_candidates',return_value=[('1','EN TALLER'),('2','EN TALLER')]), \
             patch.object(updater,'create_edge_profile',return_value='owned-profile') as profile, \
             patch.object(updater,'setup_driver',return_value=browser), \
             patch.object(updater,'login'),patch.object(updater,'open_workorders_app'), \
             patch.object(updater,'read_workorder_status',side_effect=read) as lookup, \
             patch.object(updater,'apply_reconciled_status',return_value=True), \
             patch.object(updater,'cleanup_edge_profile') as cleanup:
            low=threading.Thread(target=reconcile,daemon=True);high=threading.Thread(target=user,daemon=True)
            try:
                low.start();self.assertTrue(unit_entered.wait(2));high.start();self.assertTrue(queued.wait(2))
                unit_release.set();self.assertTrue(user_entered.wait(2));c.shutdown();low.join(3)
                self.assertFalse(low.is_alive());self.assertEqual(len(errors),1)
                self.assertIsInstance(errors[0],JobCancelled)
                self.assertEqual(lookup.call_count,1);profile.assert_called_once()
                browser.quit.assert_called_once();cleanup.assert_called_once_with('owned-profile')
            finally:
                unit_release.set();user_release.set();low.join(3);high.join(3)

    def test_update_request_reuses_existing_automatic_or_manual_work(self):
        from types import SimpleNamespace
        for first_automatic in (True, False):
            with self.subTest(first_automatic=first_automatic):
                w=SimpleNamespace(_closing=False, _list_update_pending=False,
                    _credentials_ready=Mock(return_value=True), update_lock=JobCounter(),
                    status=Mock(), _start_task=Mock())
                with patch('ui_qt.QMessageBox.information') as info:
                    MaximoDesktopWindow.update_now(w,automatic=first_automatic)
                    MaximoDesktopWindow.update_now(w,automatic=False)
                    MaximoDesktopWindow.update_now(w,automatic=True)
                self.assertEqual(w._start_task.call_count,1)
                self.assertEqual(w.update_lock.count,1)
                info.assert_called_once()
                self.assertTrue(w._list_update_pending)
                w._closing=True
                with patch('ui_qt.QMessageBox.critical'):
                    w._start_task.call_args.args[2]('test error')
                self.assertFalse(w._list_update_pending)
                self.assertFalse(w.update_lock.locked())
                w._closing=False
                MaximoDesktopWindow.update_now(w)
                self.assertEqual(w._start_task.call_count,2)

    def test_update_success_releases_duplicate_guard(self):
        from types import SimpleNamespace
        w=SimpleNamespace(_closing=False, _list_update_pending=False,
            _credentials_ready=Mock(return_value=True), update_lock=JobCounter(),
            status=Mock(), _start_task=Mock(), refresh_choices=Mock(),refresh_table=Mock(),
            _refresh_reconciliation_summary=Mock(), start_background_reconcile=Mock())
        MaximoDesktopWindow.update_now(w)
        w._start_task.call_args.args[1]((1,2))
        self.assertFalse(w._list_update_pending)
        self.assertFalse(w.update_lock.locked())
        w.start_background_reconcile.assert_called_once()
        MaximoDesktopWindow.update_now(w)
        self.assertEqual(w._start_task.call_count,2)

    def test_equal_priority_exports_finish_without_redownloading(self):
        from task_priorities import MANUAL
        c=Coordinator();entered=threading.Event();release=threading.Event();queued=threading.Event();errors=[]
        c.subscribe(lambda e:queued.set() if e['kind']=='waiting' else None)
        with tempfile.TemporaryDirectory() as folder:
            files=[Path(folder)/'one.xls',Path(folder)/'two.xls']
            for f in files:f.touch()
            calls=[]
            def download(*args):
                index=len(calls);calls.append(index)
                if index==0:entered.set();self.assertTrue(release.wait(3))
                self.assertLess(index,2,'Duplicate downloads caused by priority loop')
                return files[index]
            def work():
                try:updater.run_update(job_priority=MANUAL)
                except Exception as exc:errors.append(exc)
            with patch('task_priorities.coordinator',c),patch.object(updater,'coordinator',c), \
                 patch.object(updater,'load_config',return_value=Mock(download_dir=folder)), \
                 patch.object(updater,'_download_export_once',side_effect=download), \
                 patch.object(updater,'process_html_table',side_effect=lambda p:p), \
                 patch.object(updater,'update_database_from_df',return_value=(0,0)) as save, \
                 patch.object(updater,'cleanup_exports'):
                a=threading.Thread(target=work,daemon=True);b=threading.Thread(target=work,daemon=True)
                try:
                    a.start();self.assertTrue(entered.wait(2));b.start();self.assertTrue(queued.wait(2))
                    release.set();a.join(3);b.join(3)
                    self.assertFalse(a.is_alive());self.assertFalse(b.is_alive())
                    self.assertEqual(errors,[]);self.assertEqual(calls,[0,1])
                    self.assertEqual([call.args[0] for call in save.call_args_list],files)
                finally:release.set();a.join(3);b.join(3)

    def test_interactive_ot_opens_while_reconciliation_keeps_its_turn(self):
        from types import SimpleNamespace
        from config import AppConfig
        import maximo_client as client
        c=Coordinator();h=Harness(c);entered=threading.Event();release=threading.Event();events=[]
        c.subscribe(events.append)
        h.cfg=AppConfig();h._credentials_ready=Mock(return_value=True);h._start_task=h.start
        h.workorder_started=SimpleNamespace(emit=Mock());h.workorder_closed=SimpleNamespace(emit=Mock())
        driver=Mock()
        def reconcile():
            with c.job('Conciliación',AUTOMATIC):
                c.checkpoint('Conciliación','2966176');entered.set();release.wait(5)
        try:
            with patch('ui_qt.coordinator',c),patch.object(client,'coordinator',c), \
                 patch.object(client,'load_config',return_value=AppConfig()), \
                 patch.object(client,'create_edge_profile',return_value='interactive-profile'), \
                 patch.object(client,'setup_driver',return_value=driver), \
                 patch.object(client,'login'),patch.object(client,'open_workorders_app'), \
                 patch.object(client,'wait_for',return_value=Mock()):
                h.start(reconcile,lambda _:None,coordinated=True)
                self.wait_for(entered.is_set)
                MaximoDesktopWindow.open_ot_number(h,'4336161')
                self.wait_for(lambda:len(h.ot_sessions)==1)
                self.assertFalse(release.is_set())
                self.assertEqual(c.active.label,'Conciliación');self.assertEqual(c.queue,[])
                self.assertFalse(h.notices.dialogs)
                self.assertFalse(any(e['kind'] in ('waiting','paused') for e in events))
                self.assertEqual(h.ot_sessions[0],(driver,'interactive-profile'))
                driver.quit.assert_not_called();self.assertEqual(h.errors,[])
                release.set();self.wait_for(lambda:not h._coordinated_threads)
        finally:
            release.set();self.wait_for(lambda:not h._coordinated_threads)
            h.notices.close();h.deleteLater();self.app.processEvents()

    def test_report_preparation_remains_coordinated(self):
        from types import SimpleNamespace
        from config import AppConfig
        for action in ('print','pdf'):
            with self.subTest(action=action):
                c=Coordinator();h=Harness(c);entered=threading.Event();release=threading.Event()
                h.cfg=AppConfig();h._credentials_ready=Mock(return_value=True);h._start_task=h.start
                h.workorder_started=SimpleNamespace(emit=Mock());h.workorder_closed=SimpleNamespace(emit=Mock())
                def reconcile():
                    with c.job('Conciliación',AUTOMATIC):entered.set();release.wait(5)
                try:
                    with patch('ui_qt.coordinator',c),patch('ui_qt.open_ot',return_value=None) as open_ot:
                        h.start(reconcile,lambda _:None,coordinated=True);self.wait_for(entered.is_set)
                        MaximoDesktopWindow.open_repair_report(h,'123',action)
                        self.wait_for(lambda:bool(c.queue))
                        open_ot.assert_not_called()
                        release.set();self.wait_for(lambda:not h._coordinated_threads)
                        open_ot.assert_called_once()
                        self.assertEqual(open_ot.call_args.kwargs['report_action'],action)
                        self.assertEqual(h.errors,[])
                finally:
                    release.set();self.wait_for(lambda:not h._coordinated_threads)
                    h.notices.close();h.deleteLater();self.app.processEvents()
