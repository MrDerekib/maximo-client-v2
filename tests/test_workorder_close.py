from datetime import datetime, timedelta
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import StaleElementReferenceException

import config
import db
import workorder_close as workflow
from tests.test_support import temporary_directory

from workorder_close import repair_seconds, actual_datetime, close_review


class CloseReviewTests(TestCase):
    def test_decimal_hours_are_not_hours_and_minutes(self):
        self.assertEqual(repair_seconds('0,75'),45*60)
        self.assertEqual(repair_seconds('1,25'),75*60)
        self.assertEqual(repair_seconds('1.25'),75*60)
        self.assertEqual(repair_seconds('1'),3600)

    def test_blank_invalid_or_zero_duration_is_not_accepted(self):
        for value in ('',None,'0','-1','NaN','1:15','1,2.3','0,1','0,33','0,251','1,1'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                repair_seconds(value)

    def test_actual_dates_use_the_visible_value_or_the_date_title(self):
        expected=datetime(2026,10,26,10,0)
        self.assertEqual(actual_datetime('26/10/26 10:00:00'),expected)
        self.assertEqual(actual_datetime('', '26/10/26 10:00:00'),expected)
        self.assertIsNone(actual_datetime('',''))

    def test_end_is_calculated_and_compared_with_actual_dates(self):
        start=datetime(2026,10,26,10,0)
        review=close_review('0,75',start,datetime(2026,10,26,10,45))
        self.assertTrue(review['dates_match'])
        self.assertEqual(review['expected_end'],datetime(2026,10,26,10,45))
        self.assertFalse(close_review('1,25',start,datetime(2026,10,26,10,45))['dates_match'])

    def test_missing_start_is_not_replaced_with_the_current_time(self):
        with self.assertRaisesRegex(ValueError,'inicio real'):
            close_review('0,75',None)

    def test_close_is_opt_in_and_only_boolean_true_enables_it(self):
        self.assertFalse(config.AppConfig().workorder_close_enabled)
        self.assertTrue(config.AppConfig(workorder_close_enabled=True).workorder_close_enabled)
        self.assertFalse(config.AppConfig(workorder_close_enabled='true').workorder_close_enabled)

    def test_future_end_is_rejected_without_rounding_or_changing_start(self):
        now=datetime(2026,10,26,14,30)
        with self.assertRaisesRegex(ValueError,'hora actual'):
            workflow.validate_close_times(close_review('1',datetime(2026,10,26,14,8,16)),now)
        workflow.validate_close_times(close_review('1',datetime(2026,10,26,13,30)),now)

    def test_confirmed_close_updates_existing_active_records_only(self):
        with temporary_directory() as folder:
            path=Path(folder)/'db.sqlite'
            with closing(sqlite3.connect(path)) as conn:
                conn.execute('CREATE TABLE maximo (OT TEXT PRIMARY KEY, Seguimiento TEXT)')
                conn.executemany('INSERT INTO maximo VALUES (?,?)',[('1','INPRG'),('2','CLOSE'),('3','EN TALLER')])
                conn.commit()
            with patch.object(db,'get_connection',side_effect=lambda:sqlite3.connect(path)):
                self.assertTrue(db.apply_closed_repair('1'))
                self.assertFalse(db.apply_closed_repair('2'))
                self.assertTrue(db.apply_closed_repair('3'))
                self.assertFalse(db.apply_closed_repair('missing'))
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute('SELECT * FROM maximo ORDER BY OT').fetchall(),
                                 [('1','ISSUE'),('2','CLOSE'),('3','ISSUE')])


FIXTURE=(Path(__file__).parent/'fixtures'/'workorder_close.html').resolve().as_uri()


class FixtureCloser(workflow.WorkorderCloser):
    route_dialog_timeout=0.3

    def __init__(self,driver,ot,progress=None,timeout=2):
        super().__init__(driver,ot,progress,timeout)

    def check_location(self):
        if self.driver.current_url!=FIXTURE:
            raise AssertionError('Close test left the offline fixture')

    def response_sequence(self):
        return self.driver.execute_script('return state.responses')


@skipUnless(os.environ.get('MAXIMO_BROWSER_TESTS')=='1','Set MAXIMO_BROWSER_TESTS=1 for offline Edge tests')
class BrowserCloseTests(TestCase):
    @classmethod
    def setUpClass(cls):
        options=Options();options.add_argument('--headless=new')
        cls.browser=webdriver.Edge(options=options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()

    def setUp(self):
        self.browser.get(FIXTURE)
        self.browser.execute_script('resetState()')
        self.browser._maximo_close_review=None
        self.closer=FixtureCloser(self.browser,'4378677')

    def state(self):
        return self.browser.execute_script('return state')

    def plan(self,**overrides):
        snapshot=self.closer.inspect_repair()
        pending={'snapshot':snapshot,'created':time.monotonic(),'approved':True,'token':'offline'}
        approval={'ot':'4378677','token':'offline','duration':'1','start':'2026-10-26T10:00:00',
                  'end':'2026-10-26T11:00:00',**overrides}
        return approval,pending

    def poll(self):
        # Only the exact local fixture is allowed in this test; never Maximo.
        script=workflow.BROWSER_BUTTON_SCRIPT.replace(
            "location.origin !== 'https://eam.indraweb.net' || !location.pathname.startsWith('/maximo/ui')",
            'location.href !== '+repr(FIXTURE))
        with patch.object(workflow,'BROWSER_BUTTON_SCRIPT',script),patch.object(workflow,'WorkorderCloser',FixtureCloser):
            return workflow.poll_browser_close(self.browser)

    def prepare_dialog(self, origin='Orden de trabajo'):
        self.poll()
        if origin == 'Consumos Actuales':
            self.browser.execute_script("render('actuals')")
        self.browser.find_element(By.ID,'maximo-desktop-close-ot').click()
        self.poll()
        return self.browser.find_element(By.ID,'maximo-close-review')

    def fill_start(self,value='2026-10-26T10:00:00'):
        self.browser.execute_script("""
            const f=document.querySelector('#maximo-close-review [name=start]');
            f.value=arguments[0].slice(0,16);f.dispatchEvent(new Event('input',{bubbles:true}));
        """,value)

    def select_date_basis(self,value):
        self.browser.execute_script("""
            const f=document.querySelector(`#maximo-close-review [name=dateBasis][value="${arguments[0]}"]`);
            f.checked=true;f.dispatchEvent(new Event('change',{bubbles:true}));
        """,value)

    def fill_end(self,value):
        self.browser.execute_script("""
            const f=document.querySelector('#maximo-close-review [name=end]');
            f.value=arguments[0].slice(0,16);f.dispatchEvent(new Event('input',{bubbles:true}));
        """,value)

    def test_preparing_and_cancelling_never_changes_record_or_routes(self):
        dialog=self.prepare_dialog(origin='Consumos Actuales')
        self.assertEqual(self.browser.execute_script("return sessionStorage.getItem('close-tab')"),'actuals')
        self.assertEqual(self.state()['events'],[])
        self.assertEqual(self.state()['duration'],'')
        dialog.find_element(By.NAME,'cancel').click()
        self.poll()
        self.assertEqual(self.state()['events'],[])
        self.assertEqual(self.browser.execute_script("return sessionStorage.getItem('close-tab')"),'actuals')
        self.assertIsNone(self.browser._maximo_close_review)

    def test_review_rejects_non_quarter_hours_and_recalculates_end(self):
        dialog=self.prepare_dialog()
        self.assertEqual(dialog.find_element(By.NAME,'start').get_property('value'),'')
        self.fill_start()
        duration=dialog.find_element(By.NAME,'duration')
        duration.send_keys('0,1')
        self.assertTrue(dialog.find_element(By.NAME,'confirm').get_property('disabled'))
        duration.clear();duration.send_keys('1,25')
        self.assertEqual(dialog.find_element(By.NAME,'end').get_property('value'),'2026-10-26T11:15')
        self.assertFalse(dialog.find_element(By.NAME,'confirm').get_property('disabled'))
        self.assertEqual(self.state()['events'],[])

    def test_user_can_enter_end_and_let_the_dialog_calculate_start(self):
        dialog=self.prepare_dialog()
        self.select_date_basis('end')
        self.fill_end('2026-10-26T13:15')
        duration=dialog.find_element(By.NAME,'duration')
        duration.send_keys('1,25')
        self.assertEqual(dialog.find_element(By.NAME,'start').get_property('value'),'2026-10-26T12:00')
        self.assertEqual(dialog.find_element(By.NAME,'end').get_property('value'),'2026-10-26T13:15')
        self.assertTrue(dialog.find_element(By.NAME,'start').get_property('readOnly'))
        self.assertFalse(dialog.find_element(By.NAME,'end').get_property('readOnly'))
        self.assertFalse(dialog.find_element(By.NAME,'confirm').get_property('disabled'))

    def test_now_button_uses_current_minute_and_calculates_start(self):
        dialog=self.prepare_dialog()
        self.select_date_basis('end')
        dialog.find_element(By.NAME,'duration').send_keys('1')
        dialog.find_element(By.NAME,'now').click()
        start=datetime.strptime(dialog.find_element(By.NAME,'start').get_property('value'),'%Y-%m-%dT%H:%M')
        end=datetime.strptime(dialog.find_element(By.NAME,'end').get_property('value'),'%Y-%m-%dT%H:%M')
        self.assertEqual((end-start).total_seconds(),3600)
        self.assertLess((datetime.now()-end).total_seconds(),60)
        self.assertEqual(dialog.find_element(By.NAME,'start').get_property('step'),'300')
        self.assertEqual(dialog.find_element(By.NAME,'end').get_property('step'),'300')
        self.assertTrue(dialog.find_element(By.TAG_NAME,'form').get_property('noValidate'))

    def test_human_confirmation_persists_values_before_closing_and_consumes_approval(self):
        dialog=self.prepare_dialog(origin='Consumos Actuales')
        self.fill_start()
        dialog.find_element(By.NAME,'duration').send_keys('1')
        dialog.find_element(By.NAME,'confirm').click()
        result=self.poll()
        self.assertEqual(result,{'ot':'4378677','status':'ISSUE','action':'close'})
        state=self.state()
        self.assertEqual(state['duration'],'1')
        self.assertEqual(state['end'],'2026-10-26T11:00:00')
        events=[e[0] for e in state['events']]
        self.assertLess(events.index('route'),events.index('confirm-close'))
        self.assertEqual(events.count('confirm-close'),1)
        self.assertIsNone(self.browser._maximo_close_review)
        self.assertEqual(self.browser.execute_script("return sessionStorage.getItem('close-tab')"),'actuals')
        self.poll()
        self.assertEqual(self.state()['routes'],state['routes'])
        self.assertTrue(self.browser.find_element(By.ID,'maximo-desktop-close-ot').get_property('hidden'))

    def test_discard_and_retain_need_a_separate_checkbox_confirmation(self):
        expected={'discard':'DISCARDED','retain':'RETAINED'}
        for action,status in expected.items():
            with self.subTest(action=action):
                self.browser.execute_script('resetState()')
                dialog=self.prepare_dialog()
                dialog.find_element(By.CSS_SELECTOR,f'[name="routeAction"][value="{action}"]').click()
                self.fill_start()
                dialog.find_element(By.NAME,'duration').send_keys('1')
                dialog.find_element(By.NAME,'confirm').click()
                extra=dialog.find_element(By.ID,'maximo-route-action-confirm')
                self.assertFalse(extra.get_property('hidden'))
                execute=dialog.find_element(By.NAME,'routeActionConfirm')
                self.assertTrue(execute.get_property('disabled'))
                self.assertEqual(self.state()['routes'],0)
                self.assertEqual(self.state()['events'],[])
                dialog.find_element(By.NAME,'routeActionAck').click()
                self.assertFalse(execute.get_property('disabled'))
                execute.click()
                request=self.browser.execute_script(
                    'return JSON.parse(document.documentElement.dataset.maximoCloseOtRequest)')
                self.assertEqual(request['route_action'],action)
                self.assertTrue(request['action_confirmed'])
                result=self.poll()
                self.assertEqual(result,{'ot':'4378677','status':status,'action':action})

    def test_backend_rejects_destructive_action_without_explicit_confirmation(self):
        for action in ('discard','retain','invalid'):
            with self.subTest(action=action):
                approval,pending=self.plan(route_action=action)
                with self.assertRaises(RuntimeError):
                    self.closer.prepare_close(approval,pending)
                self.assertEqual(self.state()['routes'],0)
                self.assertEqual(self.state()['events'],[])

    def test_close_button_is_hidden_until_the_work_order_is_in_progress(self):
        self.browser.execute_script("resetState({status:'APPR'})")
        self.poll()
        button=self.browser.find_element(By.ID,'maximo-desktop-close-ot')
        self.assertTrue(button.get_property('hidden'))
        self.browser.execute_script("resetState({status:'INPRG'})")
        self.poll()
        self.assertFalse(button.get_property('hidden'))
        self.browser.execute_script("resetState({status:'ISSUE'})")
        self.poll()
        self.assertTrue(button.get_property('hidden'))

    def test_future_end_blocks_both_review_and_backend_before_any_write(self):
        start=workflow.iso_date(datetime.now()+timedelta(hours=1))
        end=workflow.iso_date(datetime.now()+timedelta(hours=2))
        approval,pending=self.plan(start=start,end=end)
        with self.assertRaisesRegex(ValueError,'hora actual'):
            self.closer.prepare_close(approval,pending)
        self.assertEqual(self.state()['events'],[])
        dialog=self.prepare_dialog()
        self.fill_start(start)
        dialog.find_element(By.NAME,'duration').send_keys('1')
        self.assertTrue(dialog.find_element(By.NAME,'confirm').get_property('disabled'))
        self.assertIn('hora actual',dialog.find_element(By.ID,'maximo-close-error').text)
        self.assertEqual(self.state()['events'],[])

    def test_locale_keyboard_entry_stages_both_date_and_time_values_until_routing(self):
        self.browser.execute_script('resetState({titleOnly:true})')
        approval,pending=self.plan()
        self.assertEqual(pending['snapshot']['start'],'2026-10-26T10:00:00')
        self.closer.prepare_close(approval,pending)
        self.assertEqual(self.state()['end'],'')
        self.assertEqual(self.browser.execute_script('return draft.end'),'2026-10-26T11:00:00')
        self.assertEqual(self.state()['routes'],0)
        self.assertIn(['end','26/10/26 11:00:00'],self.state()['events'])

    def test_dates_moving_past_old_end_change_end_first(self):
        self.browser.execute_script("resetState({duration:'1',end:'2026-10-26T11:00:00'})")
        approval,pending=self.plan(start='2026-10-26T12:00:00',end='2026-10-26T13:00:00')
        self.closer.prepare_close(approval,pending)
        events=self.state()['events']
        date_events=[(i,e) for i,e in enumerate(events) if e[0] in ('start','end')]
        changed=[e[0] for _,e in date_events]
        self.assertEqual(changed[:2],['end','start'])
        self.assertNotIn('save',events[date_events[0][0]+1:])
        self.assertEqual(self.browser.execute_script('return draft.start'),'2026-10-26T12:00:00')
        self.assertEqual(self.browser.execute_script('return draft.end'),'2026-10-26T13:00:00')

    def test_blank_end_is_filled_directly_before_routing(self):
        self.browser.execute_script("resetState({end:''})")
        approval,pending=self.plan(duration='1,25',start='2026-10-26T10:15:00',
                                   end='2026-10-26T11:30:00')
        self.closer.prepare_close(approval,pending)
        events=self.state()['events']
        date_events=[(i,e) for i,e in enumerate(events) if e[0] in ('start','end')]
        self.assertEqual([e[0] for _,e in date_events],['start','end'])
        self.assertNotIn('save',events[date_events[0][0]+1:])
        self.assertEqual(self.browser.execute_script('return draft.start'),'2026-10-26T10:15:00')
        self.assertEqual(self.browser.execute_script('return draft.end'),'2026-10-26T11:30:00')

    def test_keyboard_entry_does_not_round_start_to_quarters(self):
        self.browser.execute_script("resetState({start:'2026-10-26T14:08:16'})")
        approval,pending=self.plan(start='2026-10-26T11:07:12',end='2026-10-26T12:07:12')
        self.closer.prepare_close(approval,pending)
        self.assertEqual(self.browser.execute_script('return draft.start'),'2026-10-26T11:07:12')
        self.assertEqual(self.browser.execute_script('return draft.end'),'2026-10-26T12:07:12')
        self.assertEqual(self.state()['routes'],0)

    def test_missing_confirmation_expiry_token_or_wrong_ot_never_writes(self):
        for mutation in ('unapproved','expired','token','ot'):
            with self.subTest(mutation=mutation):
                approval,pending=self.plan()
                if mutation=='unapproved':pending['approved']=False
                elif mutation=='expired':pending['created']-=301
                else:approval[mutation]='wrong'
                with self.assertRaises(RuntimeError):self.closer.prepare_close(approval,pending)
                self.assertEqual(self.state()['events'],[])

    def test_record_changed_after_review_stops_before_writes(self):
        approval,pending=self.plan()
        self.browser.execute_script("state.start='2026-10-26T09:00:00';persist()")
        with self.assertRaisesRegex(RuntimeError,'cambiaron'):
            self.closer.prepare_close(approval,pending)
        self.assertEqual(self.state()['events'],[])

    def test_invalid_duration_or_mismatched_end_never_writes(self):
        for duration,end in (('0,1','2026-10-26T10:06:00'),('1','2026-10-26T12:00:00')):
            approval,pending=self.plan(duration=duration,end=end)
            with self.assertRaises((ValueError,RuntimeError)):self.closer.prepare_close(approval,pending)
            self.assertEqual(self.state()['events'],[])

    def test_noop_route_retries_bounded_known_warning_then_stops_at_issue(self):
        self.browser.execute_script('resetState({noOpRoutes:1,warning:true})')
        self.closer.route_close()
        self.assertEqual(self.state()['status'],'ISSUE')
        self.assertEqual(self.state()['routes'],3)
        self.closer.route_close()
        self.assertEqual(self.state()['routes'],3)

    def test_unknown_dialog_or_unexpected_choice_is_never_accepted(self):
        for flag in ('unknownDialog','wrongChoice'):
            with self.subTest(flag=flag):
                self.browser.execute_script('resetState(arguments[0])',{flag:True})
                with self.assertRaises(RuntimeError):self.closer.route_close()
                self.assertFalse(any(e[0] in ('confirm-close','unsafe','close') for e in self.state()['events']))

    def test_uncertain_final_accept_is_not_repeated(self):
        self.browser.execute_script('resetState({noConfirmation:true})')
        with self.assertRaises(RuntimeError):self.closer.route_close()
        self.assertEqual([e[0] for e in self.state()['events']].count('confirm-close'),1)
        self.assertEqual(self.state()['routes'],1)

    def test_stale_after_final_accept_checks_result_without_replaying(self):
        original=WebElement.click
        def clicked(element):
            result=original(element)
            if element.tag_name=='button' and element.text=='Aceptar':
                raise StaleElementReferenceException('Response replaced button after dispatch')
            return result
        with patch.object(WebElement,'click',clicked):self.closer.route_close()
        self.assertEqual(self.state()['status'],'ISSUE')
        self.assertEqual([e[0] for e in self.state()['events']].count('confirm-close'),1)

    def test_ineligible_status_cannot_start_review_or_route(self):
        for status in ('APPR','ISSUE','CLOSE'):
            self.browser.execute_script('resetState(arguments[0])',{'status':status})
            self.poll()
            self.assertTrue(self.browser.find_element(By.ID,'maximo-desktop-close-ot').get_property('hidden'))
            with self.assertRaises(RuntimeError):self.closer.inspect_repair()
            with self.assertRaises(RuntimeError):self.closer.require_in_progress()
            if status!='ISSUE':
                with self.assertRaises(RuntimeError):self.closer.route_close()
            self.assertEqual(self.state()['routes'],0)
