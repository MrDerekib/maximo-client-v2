import tests  # Isolate application data before importing product modules.
import threading
from unittest import TestCase
from task_priorities import Coordinator, JobCounter, JobCancelled, HIGH, MANUAL, AUTOMATIC


class PriorityTests(TestCase):
    def start(self, function):
        errors=[]
        def work():
            try:function()
            except BaseException as exc:errors.append(exc)
        thread=threading.Thread(target=work,daemon=True);thread.start()
        self.addCleanup(thread.join,2)
        return thread,errors

    def finish(self,*workers):
        for thread,errors in workers:
            thread.join(3)
            self.assertFalse(thread.is_alive(),'Coordinator deadlock')
            self.assertEqual(errors,[])

    def test_finishes_current_ot_closes_browser_then_runs_user_and_resumes(self):
        c=Coordinator();entered=threading.Event();release=threading.Event();queued=threading.Event();events=[];notifications=[]
        self.addCleanup(release.set)
        def listener(e):
            notifications.append(e)
            if e['kind']=='waiting' and e['priority']==HIGH:queued.set()
        c.subscribe(listener)
        def background():
            with c.job('Conciliación',AUTOMATIC):
                c.checkpoint('Conciliación','123',0,3)
                entered.set();self.assertTrue(release.wait(2));events.append('ot_saved')
                c.checkpoint('Conciliación','456',1,3,on_pause=lambda:events.append('browser_closed'))
                events.append('resume')
        def user():
            with c.job('Confirmar recepción',HIGH):events.append('user')
        low=self.start(background);self.assertTrue(entered.wait(2))
        high=self.start(user);self.assertTrue(queued.wait(2));self.assertEqual(events,[])
        release.set();self.finish(low,high)
        self.assertEqual(events,['ot_saved','browser_closed','user','resume'])
        wait=next(e for e in notifications if e['kind']=='waiting')
        self.assertIn('123',wait['message']);self.assertIn('Confirmar recepción',wait['message'])
        resumed=next(e for e in notifications if e['kind']=='resumed')
        self.assertEqual((resumed['completed'],resumed['total']),(1,3))

    def test_background_never_interrupts_active_user(self):
        c=Coordinator();entered=threading.Event();release=threading.Event();queued=threading.Event();events=[]
        self.addCleanup(release.set)
        c.subscribe(lambda e:queued.set() if e['kind']=='waiting' else None)
        def user():
            with c.job('Salida',HIGH):
                entered.set();self.assertTrue(release.wait(2))
                self.assertFalse(c.checkpoint('Verificación','1'))
                events.append('user_done')
        def automatic():
            with c.job('Automática',AUTOMATIC):events.append('automatic')
        high=self.start(user);self.assertTrue(entered.wait(2));low=self.start(automatic)
        self.assertTrue(queued.wait(2));self.assertEqual(events,[])
        release.set();self.finish(high,low);self.assertEqual(events,['user_done','automatic'])

    def test_manual_precedes_older_automatic_request(self):
        c=Coordinator();entered=threading.Event();release=threading.Event();auto_queued=threading.Event();manual_queued=threading.Event();events=[]
        self.addCleanup(release.set)
        c.subscribe(lambda e:(auto_queued if e['priority']==AUTOMATIC else manual_queued).set() if e['kind']=='waiting' else None)
        def holder():
            with c.job('Actual',HIGH):entered.set();self.assertTrue(release.wait(2))
        def request(label,priority):
            with c.job(label,priority):events.append(label)
        current=self.start(holder);self.assertTrue(entered.wait(2))
        low=self.start(lambda:request('Auto',AUTOMATIC));self.assertTrue(auto_queued.wait(2))
        manual=self.start(lambda:request('Manual',MANUAL));self.assertTrue(manual_queued.wait(2))
        release.set();self.finish(current,low,manual);self.assertEqual(events,['Manual','Auto'])

    def test_equal_priority_runs_in_order_without_yielding_or_ping_pong(self):
        c=Coordinator();entered=threading.Event();release=threading.Event();queued=threading.Event();events=[]
        self.addCleanup(release.set);c.subscribe(lambda e:queued.set() if e['kind']=='waiting' else None)
        def first():
            with c.job('Lote',HIGH):
                entered.set();self.assertTrue(release.wait(2));events.append('first_ot')
                self.assertFalse(c.checkpoint('Siguiente OT'));events.append('second_ot')
        def second():
            with c.job('Individual',HIGH):
                self.assertFalse(c.checkpoint('Preparando'));events.append('individual')
        a=self.start(first);self.assertTrue(entered.wait(2));b=self.start(second);self.assertTrue(queued.wait(2))
        release.set();self.finish(a,b);self.assertEqual(events,['first_ot','second_ot','individual'])

    def test_shutdown_cancels_queue_but_does_not_cut_active_confirmation(self):
        c=Coordinator();entered=threading.Event();release=threading.Event();queued=threading.Event();events=[]
        self.addCleanup(release.set);c.subscribe(lambda e:queued.set() if e['kind']=='waiting' else None)
        def active():
            with c.job('Confirmación',HIGH):entered.set();self.assertTrue(release.wait(2));events.append('verified')
        def pending():
            with self.assertRaises(JobCancelled):
                with c.job('Pendiente',AUTOMATIC):events.append('not_allowed')
        a=self.start(active);self.assertTrue(entered.wait(2));b=self.start(pending);self.assertTrue(queued.wait(2))
        c.shutdown();b[0].join(2);self.assertEqual(events,[])
        release.set();self.finish(a,b);self.assertEqual(events,['verified'])

    def test_global_read_yield_requires_explicit_read_scope(self):
        c=Coordinator();entered=threading.Event();release=threading.Event();queued=threading.Event()
        self.addCleanup(release.set);c.subscribe(lambda e:queued.set() if e['kind']=='waiting' else None)
        def background():
            with c.job('Descarga',AUTOMATIC):
                entered.set();self.assertTrue(release.wait(2))
                self.assertFalse(c.should_yield_read())
                with c.interruptible_read():self.assertTrue(c.should_yield_read())
                self.assertFalse(c.should_yield_read())
        def user():
            with c.job('Usuario',HIGH):pass
        a=self.start(background);self.assertTrue(entered.wait(2));b=self.start(user);self.assertTrue(queued.wait(2))
        release.set();self.finish(a,b)

    def test_job_counter_is_only_an_activity_counter_not_a_mutex(self):
        counter=JobCounter();self.assertTrue(counter.acquire(False));self.assertTrue(counter.acquire(False))
        counter.release();self.assertTrue(counter.locked());counter.release();self.assertFalse(counter.locked())
        with self.assertRaises(RuntimeError):counter.release()
