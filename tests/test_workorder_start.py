"""Tests of explicit start semantics and the Maximo asynchronous workflow."""
import os
import json
import sqlite3
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException

import config
import db
import maximo_client as client
import workorder_start as workflow
from tests.test_support import temporary_directory


class StartConfigurationTests(TestCase):
    def test_invalid_change_requests_never_fall_back_to_starting(self):
        for action,mode,selection in (('change_anomalies','only',None),
                                      ('change_anomalies','configured',None),
                                      ('unknown','configured',{})):
            driver = Mock()
            request = json.dumps({'ot':'4314531','action':action,'mode':mode,'selection':selection})
            driver.execute_script.side_effect = [True,None,True,request,None]
            with self.subTest(action=action,mode=mode), \
                 patch.object(workflow,'_start_options_source',return_value='/*fixture*/'), \
                 patch.object(workflow,'start_workorder') as start, \
                 patch.object(workflow,'change_workorder_anomalies') as change:
                self.assertIsNone(workflow.poll_browser_start(driver))
            start.assert_not_called()
            change.assert_not_called()

    def test_explicit_invalid_start_mode_is_rejected_before_any_navigation(self):
        starter = workflow.WorkorderStarter(Mock(current_url='https://eam.indraweb.net/maximo/ui'), '4314531')
        starter.check_location = Mock()
        starter.wait = Mock()
        starter.check_ot = Mock()
        starter.value = Mock(return_value='APPR')
        starter.dialogs = Mock(return_value=[])
        starter.tab = Mock()
        starter.route = Mock()
        for mode in (None, '', 'invalid'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'modo de inicio'):
                starter.run(anomaly_mode=mode)
        starter.tab.assert_not_called()
        starter.route.assert_not_called()

    def test_malformed_browser_mode_is_completed_without_running_or_sticking_busy(self):
        driver = Mock()
        payload = json.dumps({'ot':'4314531','returnTab':'Orden de trabajo','selection':{},'mode':None})
        driver.execute_script.side_effect = [True, None, True, payload, None]
        with patch.object(workflow, '_start_options_source', return_value='/*fixture*/'), \
             patch.object(workflow, 'start_workorder') as start:
            self.assertIsNone(workflow.poll_browser_start(driver))
        start.assert_not_called()
        self.assertIn('Solicitud de inicio no válida', driver.execute_script.call_args.args[0])

    def test_stale_click_reacquires_only_the_target(self):
        stale, fresh = Mock(), Mock()
        stale.click.side_effect = StaleElementReferenceException('redrawn')
        find = Mock(side_effect=[stale, fresh])
        starter = workflow.WorkorderStarter(Mock(), '4314531', timeout=1)
        starter.check_ot = Mock()
        self.assertTrue(starter.click_fresh(find, 'Continuar'))
        self.assertEqual(find.call_count, 2)
        fresh.click.assert_called_once()

    def test_click_is_not_repeated_if_its_effect_is_already_visible(self):
        state = {'done': False}
        def accepted():
            state['done'] = True
            raise StaleElementReferenceException('removed after acceptance')
        target = Mock()
        target.click.side_effect = accepted
        find = Mock(return_value=target)
        starter = workflow.WorkorderStarter(Mock(), '4314531', timeout=1)
        starter.check_ot = Mock()
        self.assertFalse(starter.click_fresh(find, 'Aceptar', completed=lambda: state['done']))
        find.assert_called_once()
        target.click.assert_called_once()

    def test_technical_browser_errors_are_logged_but_not_shown_in_the_button(self):
        error = StaleElementReferenceException('technical details with Stacktrace')
        self.assertNotIn('Stacktrace', workflow.browser_error_message(error))
        with patch.object(workflow, 'WorkorderStarter') as starter:
            starter.return_value.run.side_effect = error
            with self.assertRaisesRegex(RuntimeError, 'Maximo actualizó la pantalla'):
                workflow.start_workorder(Mock(), '4314531')
        starter.return_value.run.assert_called_once()
        self.assertNotIn('Stacktrace', workflow.browser_error_message(WebDriverException('Stacktrace')))

    def test_start_is_opt_in_and_invalid_values_cannot_enable_it(self):
        self.assertFalse(config.AppConfig().workorder_start_enabled)
        self.assertTrue(config.AppConfig(workorder_start_enabled=True).workorder_start_enabled)
        self.assertFalse(config.AppConfig(workorder_start_enabled='true').workorder_start_enabled)

    def test_opening_does_not_start_a_workorder_even_when_feature_is_enabled(self):
        cfg = SimpleNamespace(workorder_start_enabled=True, repair_extension_enabled=False)
        driver = Mock()
        with patch.object(client, 'load_config', return_value=cfg), \
             patch.object(client, 'create_edge_profile', return_value='test-profile'), \
             patch.object(client, 'setup_driver', return_value=driver), \
             patch.object(client, 'login'), patch.object(client, 'open_workorders_app'), \
             patch.object(client, 'wait_for'), patch.object(client, '_start_ot_action_watcher') as watcher, \
             patch.object(workflow, 'start_workorder') as start:
            session = client.open_ot('4314531')
        self.assertIs(session[0], driver)
        start.assert_not_called()
        watcher.assert_called_once_with(driver)
        self.assertTrue(driver._maximo_workorder_start_enabled)
        driver.quit.assert_not_called()

    def test_desktop_headless_start_entry_points_are_removed(self):
        self.assertFalse(hasattr(client, 'start_ot'))
        with patch.object(client,'setup_driver') as setup:
            with self.assertRaises(TypeError):
                client.open_ot('4314531',headless=True,start_workflow=True)
        setup.assert_not_called()

    def test_close_is_exposed_only_in_visible_sessions_and_open_never_closes(self):
        cfg=SimpleNamespace(workorder_start_enabled=False,workorder_close_enabled=True,repair_extension_enabled=False)
        for headless in (False,True):
            with self.subTest(headless=headless):
                driver=Mock()
                callback=Mock()
                with patch.object(client,'load_config',return_value=cfg), \
                     patch.object(client,'create_edge_profile',return_value='test-profile'), \
                     patch.object(client,'cleanup_edge_profile'), \
                     patch.object(client,'setup_driver',return_value=driver), \
                     patch.object(client,'login'),patch.object(client,'open_workorders_app'), \
                     patch.object(client,'wait_for'),patch.object(client,'_start_ot_action_watcher') as watcher, \
                     patch('workorder_close.poll_browser_close') as close:
                    client.open_ot('4378677',headless=headless,on_workorder_closed=callback)
                close.assert_not_called()
                callback.assert_not_called()
                if headless:
                    watcher.assert_not_called()
                    self.assertNotIn('_maximo_workorder_close_enabled',driver.__dict__)
                else:
                    watcher.assert_called_once_with(driver)
                    self.assertTrue(driver._maximo_workorder_close_enabled)
                    self.assertIs(driver._maximo_workorder_closed,callback)

    def test_start_location_must_be_the_configured_maximo_site(self):
        for url in ('https://example.org/maximo/ui/', 'http://eam.indraweb.net/maximo/ui/',
                    'https://eam.indraweb.net/unrelated'):
            with self.subTest(url=url), self.assertRaisesRegex(RuntimeError, 'ficha de Maximo'):
                workflow.WorkorderStarter(SimpleNamespace(current_url=url), '4314531').check_location()

    def test_confirmed_start_does_not_overwrite_a_later_closed_state_or_create_records(self):
        with temporary_directory() as folder:
            path = Path(folder) / 'db.sqlite'
            with closing(sqlite3.connect(path)) as connection:
                connection.execute('CREATE TABLE maximo (OT TEXT PRIMARY KEY, Seguimiento TEXT)')
                connection.executemany('INSERT INTO maximo VALUES (?, ?)', [('1','APPR'),('2','CLOSE'),('3','EN TALLER')])
                connection.commit()
            with patch.object(db, 'get_connection', side_effect=lambda: sqlite3.connect(path)):
                self.assertTrue(db.apply_started_workorder('1'))
                self.assertTrue(db.apply_started_workorder('3'))
                self.assertFalse(db.apply_started_workorder('2'))
                self.assertFalse(db.apply_started_workorder('missing'))
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute('SELECT * FROM maximo ORDER BY OT').fetchall(),
                                 [('1','INPRG'),('2','CLOSE'),('3','INPRG')])


FIXTURE = (Path(__file__).parent / 'fixtures' / 'workorder_start.html').resolve().as_uri()


class FixtureStarter(workflow.WorkorderStarter):
    route_dialog_timeout = 0.5

    def response_sequence(self):
        # The offline fixture models server replies without making HTTP calls.
        return self.driver.execute_script('return state.responses')

    def check_location(self):
        # This suite only drives the committed local HTML fixture, never Maximo.
        if self.driver.current_url != FIXTURE:
            raise AssertionError('Browser test left the local fixture')


class FixtureAnomalyChanger(workflow.WorkorderAnomalyChanger, FixtureStarter):
    pass


@skipUnless(os.environ.get('MAXIMO_BROWSER_TESTS') == '1', 'Set MAXIMO_BROWSER_TESTS=1 for offline Edge tests')
class BrowserStartTests(TestCase):
    @classmethod
    def setUpClass(cls):
        options = Options()
        options.add_argument('--headless=new')
        cls.browser = webdriver.Edge(options=options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()

    def setUp(self):
        self.browser.get(FIXTURE)
        self.browser.execute_script('resetState()')

    def run_fixture(self, return_tab=None, anomaly_mode="configured", anomaly_selection=None, **state):
        self.browser.execute_script('resetState(arguments[0])', state)
        return FixtureStarter(self.browser, '4314531', timeout=5).run(return_tab=return_tab,
            anomaly_mode=anomaly_mode, anomaly_selection=anomaly_selection)

    def maximo_page_scripts(self):
        original = self.browser.execute_script
        def execute(script, *args):
            if script == "return location.origin === 'https://eam.indraweb.net' && location.pathname.startsWith('/maximo/ui')":
                return True
            return original(script, *args)
        return patch.object(self.browser, 'execute_script', side_effect=execute)

    def test_start_returns_to_the_tab_where_the_user_launched_it(self):
        self.run_fixture(return_tab='Informes de anomalías', faultclass='RFN-70',
                         problem='OTROS-01', cause='OTROS-02', remedy='OTROS-03')
        self.assertEqual(self.browser.execute_script("return sessionStorage.getItem('workflow-fixture-tab')"), 'anomaly')

    def test_diagnostics_keep_consulted_options_and_missing_filtered_result(self):
        self.browser.execute_script("resetState({faultclass:'RFN-70',problem:'',cause:'',remedy:'',nativeMissingCode:'OTROS-01'});render('anomaly')")
        starter = FixtureStarter(self.browser, '4314531', timeout=1)
        starter.begin_anomaly_diagnostics('configured', {})
        with self.assertRaisesRegex(RuntimeError, 'tras filtrar'):
            starter.select_failure_codes(path=[{'type':'PROBLEM','code':'OTROS-01'}])
        snapshots = starter.anomaly_diagnostic_snapshots
        self.assertTrue(any(not s.get('filter') and s['options'][0]['code']=='UNEXPECTED' for s in snapshots))
        self.assertTrue(any(s.get('filter')=='=OTROS-01' for s in snapshots))
        self.assertTrue(all(s['options'][0]['description']=='Descripción' for s in snapshots if s['options']))
        self.assertEqual(self.browser.execute_script('return state.routes'), 0)

    def test_configured_success_does_not_write_an_incident(self):
        with patch.object(workflow, 'record_anomaly_incident') as record:
            self.run_fixture()
        record.assert_not_called()

    def test_empty_or_different_class_is_selected_before_the_solutions_and_persisted(self):
        for initial in ('', 'OTHER'):
            with self.subTest(initial=initial):
                result = self.run_fixture(faultclass=initial)
                self.assertFalse(result['already_started'])
                state = self.browser.execute_script('return state')
                self.assertEqual(state['status'], 'INPRG')
                self.assertEqual(state['routes'], 2)
                self.assertEqual([event for event in state['events'] if event[0]=='select'], [
                    ['select','faultclass','RFN-70'],['select','problem','OTROS-01'],
                    ['select','cause','OTROS-02'],['select','remedy','OTROS-03'],
                ])
                self.assertEqual(state['events'].count(['start']), 1)
                self.assertFalse(state['pendingDeletion'])
                self.assertEqual(state['events'].count(['save']), 3)
                self.assertEqual(state['events'].count(['native-open']), 1)
                self.assertFalse(any(e[0]=='unexpected-selector-button' for e in state['events']))
                self.assertFalse(any(e[0]=='lookup' and e[1]!='faultclass' for e in state['events']))

    def test_pending_deletions_are_saved_before_selecting_children(self):
        self.run_fixture(faultclass='RFN-70', pendingDeletion=True, saveWarning=True)
        state = self.browser.execute_script('return state')
        self.assertEqual(next(e for e in state['events'] if e[0] in {'save','native-open'}), ['save'])
        self.assertFalse(state['pendingDeletion'])
        self.assertTrue(state['saveWarningShown'])
        self.assertEqual(state['status'], 'INPRG')

    def test_native_hierarchy_avoids_the_problematic_solution_inputs(self):
        self.run_fixture(faultclass='RFN-70', forceHierarchyError=True)
        events = self.browser.execute_script('return state.events')
        self.assertEqual([e for e in events if e[0]=='native-click'], [
            ['native-click','PROBLEM','OTROS-01'],['native-click','CAUSE','OTROS-02'],
            ['native-click','REMEDY','OTROS-03'],
        ])
        self.assertFalse(any(e[0]=='lookup' for e in events))
        self.assertEqual(events.count(['save']), 2)

    def test_terminal_problem_path_is_supported_without_assumed_levels(self):
        path=[{"type":"PROBLEM","code":"LG-01","key":"test-lg-root","allow_duplicate":False}]
        selection={"class_key":"TRANSPORTES|RFN-70","option_keys":["test-lg-root"]}
        with patch.object(workflow,"resolve_selection",return_value={"class_key":selection["class_key"],
                "class_code":"RFN-70","organization":"TRANSPORTES","path":path}):
            self.run_fixture(faultclass='RFN-70',problem='',cause='',remedy='',
                nativeHierarchy=[{"type":"PROBLEM","key":"problem","code":"LG-01",
                                  "options":["LG-00","LG-01"],"pageSize":1}],
                anomaly_selection=selection)
        state=self.browser.execute_script('return state')
        self.assertEqual([e for e in state['events'] if e[0]=='native-click'],[['native-click','PROBLEM','LG-01']])
        self.assertEqual(state['status'],'INPRG')

    def test_direct_cause_and_two_level_paths_are_supported(self):
        cases=[
            ([{"type":"CAUSE","code":"CD-19-0-3","key":"c","allow_duplicate":False}],
             [{"type":"CAUSE","key":"cause","code":"CD-19-0-3"}]),
            ([{"type":"PROBLEM","code":"FGV-01","key":"p","allow_duplicate":False},
              {"type":"CAUSE","code":"FGV-02","key":"c","allow_duplicate":False}],
             [{"type":"PROBLEM","key":"problem","code":"FGV-01"},
              {"type":"CAUSE","key":"cause","code":"FGV-02"}]),
        ]
        for path,hierarchy in cases:
            with self.subTest(path=path):
                selection={"class_key":"TRANSPORTES|RFN-70","option_keys":[item["key"] for item in path]}
                resolved={"class_key":selection["class_key"],"class_code":"RFN-70",
                          "organization":"TRANSPORTES","path":path}
                self.browser.execute_script('resetState(arguments[0])',
                    {"faultclass":"RFN-70","problem":"","cause":"","remedy":"","nativeHierarchy":hierarchy})
                with patch.object(workflow,"resolve_selection",return_value=resolved):
                    FixtureStarter(self.browser,'4314531',timeout=5).run(anomaly_selection=selection)
                self.assertEqual(self.browser.execute_script('return state.status'),'INPRG')
                self.assertEqual([event for event in self.browser.execute_script('return state.events') if event[0]=='native-click'],
                                 [["native-click",item["type"],item["code"]] for item in path])

    def test_invalid_selection_stops_before_edits_or_routing(self):
        with self.assertRaises(ValueError):
            self.run_fixture(anomaly_selection={})
        state=self.browser.execute_script('return state')
        self.assertEqual(state['events'],[])
        self.assertEqual(state['routes'],0)

    def test_only_mode_routes_without_reading_or_changing_anomalies(self):
        starter=FixtureStarter(self.browser,'4314531',timeout=5)
        starter.solution_codes=Mock(side_effect=AssertionError('only mode must not inspect solution codes'))
        result=starter.run(anomaly_mode='only')
        self.assertEqual(result['status'],'INPRG')
        events=self.browser.execute_script('return state.events')
        self.assertEqual(events.count(['start']),1)
        self.assertFalse(any(event[0] in {'select','native-open','suppress'} for event in events))

    def test_bmxaa4523e_is_reported_immediately_without_accepting_or_routing(self):
        with self.assertRaisesRegex(RuntimeError, 'BMXAA4523E'):
            self.run_fixture(faultclass='RFN-70', forceNativeError=True)
        state = self.browser.execute_script('return state')
        self.assertEqual(state['routes'], 0)
        self.assertEqual(len(self.browser.find_elements(By.ID, 'warndiv')), 1)
        self.assertEqual(FixtureStarter(self.browser, '4314531').dialog_snapshot()[-1]['id'], 'warndiv')

    def test_missing_or_wrong_native_code_stops_before_routing(self):
        for state in ({'nativeMissingCode':'OTROS-03'}, {'nativeWrongType':'UNKNOWN'}):
            with self.subTest(state=state), self.assertRaisesRegex(RuntimeError, 'opción|nivel|selector muestra'):
                self.run_fixture(**state)
            self.assertEqual(self.browser.execute_script('return state.routes'), 0)

    def test_early_native_close_is_verified_in_solutions_before_routing(self):
        with self.assertRaisesRegex(RuntimeError, 'OTROS-02'):
            self.run_fixture(nativeCloseEarly=True)
        self.assertEqual(self.browser.execute_script('return state.routes'), 0)

    def test_native_selector_can_start_at_a_confirmed_partial_hierarchy(self):
        self.run_fixture(faultclass='RFN-70', problem='OTROS-01', cause='', remedy='', nativeInitialStage=1)
        clicks = self.browser.execute_script("return state.events.filter(e=>e[0]==='native-click')")
        self.assertEqual(clicks,[['native-click','CAUSE','OTROS-02'],['native-click','REMEDY','OTROS-03']])

    def test_native_selector_does_not_skip_an_unconfirmed_parent(self):
        with self.assertRaisesRegex(RuntimeError, 'selector muestra CAUSE'):
            self.run_fixture(faultclass='RFN-70', problem='', nativeInitialStage=1)
        self.assertEqual(self.browser.execute_script('return state.routes'), 0)

    def test_solution_verification_waits_for_the_fields_to_be_rendered(self):
        self.browser.execute_script("""
            const fields=[...document.querySelectorAll('label[for]')]
              .filter(label=>['Síntoma:','Causa:','Resolucion:'].includes(label.textContent.trim()))
              .map(label=>document.getElementById(label.htmlFor));
            const parents=fields.map(field=>field.parentElement);
            fields.forEach(field=>field.remove());
            setTimeout(()=>fields.forEach((field,index)=>parents[index].appendChild(field)),200);
        """)
        starter = FixtureStarter(self.browser, '4314531', timeout=5)
        self.assertEqual(starter.solution_codes(),{'PROBLEM':'OLD-01','CAUSE':'OLD-02','REMEDY':'OLD-03'})

    def test_native_rows_are_relocated_if_the_dialog_is_replaced_before_the_click(self):
        original_click = WebElement.click
        redraws = []
        def redraw_then_click(element):
            if not redraws and element.tag_name == 'span' and element.text == 'OTROS-02':
                self.browser.execute_script("const d=arguments[0].closest('[role=dialog]');d.replaceWith(d.cloneNode(true));", element)
                redraws.append(True)
            return original_click(element)
        with patch.object(WebElement, 'click', redraw_then_click):
            self.run_fixture(nativeDelayMs=200)
        self.assertEqual(len(redraws),1)
        self.assertEqual(self.browser.execute_script("return state.events.filter(e=>e[0]==='native-click').length"),3)

    def test_closed_warning_shell_does_not_block_start(self):
        starter = FixtureStarter(self.browser, '4314531', timeout=5)
        self.assertEqual(starter.dialog_snapshot(), [])
        self.assertEqual(starter.dialogs(), [])
        self.assertEqual(starter.run()['status'], 'INPRG')

    def test_a_visible_warning_in_the_zero_width_shell_still_blocks_start(self):
        self.browser.execute_script("showWarning('BMXAA4523E - Mensaje del sistema')")
        starter = FixtureStarter(self.browser, '4314531', timeout=5)
        self.assertEqual(starter.dialog_snapshot()[0]['id'], 'warndiv')
        with self.assertRaisesRegex(RuntimeError, 'Cierra el diálogo'):
            starter.run()
        self.assertEqual(self.browser.execute_script('return state.events'), [])

    def test_zero_area_transparent_or_aria_hidden_dialogs_are_not_active(self):
        self.browser.execute_script("""
            for (const attributes of [
              {style:'width:0;height:100px'}, {style:'width:100px;height:100px;opacity:0'},
              {style:'width:100px;height:100px', 'aria-hidden':'true'}]) {
              const dialog=document.createElement('div'); dialog.role='dialog';
              for (const [key,value] of Object.entries(attributes)) dialog.setAttribute(key,value);
              dialog.textContent='Aviso retenido'; document.body.appendChild(dialog);
            }
        """)
        starter = FixtureStarter(self.browser, '4314531')
        self.assertEqual(starter.dialog_snapshot(), [])
        self.assertEqual(starter.dialogs(), [])

    def test_browser_button_uses_the_same_active_dialog_detection(self):
        original = self.browser.execute_script
        with self.maximo_page_scripts():
            workflow.poll_browser_start(self.browser)
            button = self.browser.find_element(By.ID, 'maximo-desktop-start-ot')
            self.assertTrue(button.is_enabled())
            original("showWarning('BMXAA4523E - Mensaje del sistema')")
            workflow.poll_browser_start(self.browser)
            self.assertFalse(button.is_enabled())
            original('hideWarning()')
            workflow.poll_browser_start(self.browser)
            self.assertTrue(button.is_enabled())
        self.assertEqual(original('return state.events'), [])

    def test_start_button_is_hidden_after_the_order_has_started(self):
        original = self.browser.execute_script
        with self.maximo_page_scripts():
            workflow.poll_browser_start(self.browser)
            button = self.browser.find_element(By.ID, 'maximo-desktop-start-ot')
            self.assertFalse(button.get_property('hidden'))
            original("state.status='INPRG';render(tab)")
            workflow.poll_browser_start(self.browser)
            self.assertTrue(button.get_property('hidden'))

    def test_start_button_click_captures_the_current_tab_for_return(self):
        original = self.browser.execute_script
        with self.maximo_page_scripts():
            workflow.poll_browser_start(self.browser)
            original("render('anomaly')")
            self.browser.find_element(By.ID, 'maximo-desktop-start-ot').click()
            with patch.object(workflow, 'start_workorder', return_value={'already_started': False,'status':'INPRG'}) as start:
                workflow.poll_browser_start(self.browser)
        self.assertEqual(start.call_args.kwargs['return_tab'], 'Informes de anomalías')

    def test_manual_start_choice_supports_aria_and_single_radio_containers(self):
        for markup in ('aria','container'):
            with self.subTest(markup=markup):
                self.run_fixture(radioMarkup=markup)
                self.assertEqual(self.browser.execute_script('return state.events').count(['start']), 1)

    def test_routing_retries_a_click_that_did_not_open_any_dialog(self):
        for count in (1, 2):
            with self.subTest(no_op_clicks=count):
                self.run_fixture(noOpRoutes=count)
                state = self.browser.execute_script('return state')
                self.assertEqual(state['routes'], count + 1)
                self.assertEqual(state['events'].count(['start']), 1)

    def test_routing_stops_after_three_clicks_without_an_effect(self):
        with self.assertRaisesRegex(RuntimeError, 'tres intentos'):
            self.run_fixture(noOpRoutes=10)
        state = self.browser.execute_script('return state')
        self.assertEqual(state['routes'], 3)
        self.assertEqual(state['status'], 'APPR')
        self.assertNotIn(['start'], state['events'])

    def test_routing_does_not_click_again_while_maximo_is_loading_the_dialog(self):
        self.run_fixture(routeDelayMs=900)
        state = self.browser.execute_script('return state')
        self.assertEqual(state['routes'], 2)
        self.assertEqual(state['events'].count(['start']), 1)

    def test_continue_button_is_relocated_after_the_whole_dialog_is_redrawn(self):
        original_click = WebElement.click
        redraws = []
        def redraw_then_click(element):
            if not redraws and element.tag_name == 'button' and element.text == 'Continuar':
                self.browser.execute_script("const d=arguments[0].closest('[role=dialog]'); d.replaceWith(d.cloneNode(true));", element)
                redraws.append(True)
            return original_click(element)
        with patch.object(WebElement, 'click', redraw_then_click):
            self.run_fixture()
        self.assertEqual(len(redraws), 1)
        events = self.browser.execute_script('return state.events')
        self.assertEqual(events.count(['continue']), 1)
        self.assertEqual(events.count(['start']), 1)

    def test_final_accept_is_not_replayed_if_maximo_replaces_it_after_dispatch(self):
        original_click = WebElement.click
        dispatched = []
        def accepted_then_stale(element):
            if not dispatched and element.tag_name == 'button' and element.text == 'Aceptar':
                dispatched.append(True)
                original_click(element)
                raise StaleElementReferenceException('button removed after request was sent')
            return original_click(element)
        with patch.object(WebElement, 'click', accepted_then_stale):
            self.run_fixture()
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(self.browser.execute_script('return state.events').count(['start']), 1)

    def test_save_response_observer_sees_real_local_ajax_completion(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(b'<!doctype html><title>Local response test</title>')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.browser.get(f'http://127.0.0.1:{server.server_port}/')
            starter = workflow.WorkorderStarter(self.browser, '4314531', timeout=5)
            baseline = starter.response_sequence()
            self.browser.execute_async_script("""
                const done = arguments[0];
                fetch('/maximo/ui/maximo.jsp').then(r => r.text()).then(() => done(true));
            """)
            self.assertTrue(starter.wait(lambda d: starter.response_sequence() > baseline, 'respuesta local'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_an_in_progress_workorder_is_not_edited_or_routed_again(self):
        result = self.run_fixture(status='INPRG')
        self.assertTrue(result['already_started'])
        self.assertEqual(self.browser.execute_script('return state.events'), [])

    def test_preexisting_correct_codes_are_kept_and_the_order_is_started_once(self):
        self.run_fixture(faultclass='RFN-70', problem='OTROS-01', cause='OTROS-02', remedy='OTROS-03')
        events = self.browser.execute_script('return state.events')
        self.assertFalse(any(event[0]=='select' for event in events))
        self.assertNotIn(['native-open'],events)
        self.assertEqual(events.count(['start']), 1)

    def test_preexisting_route_with_marked_extra_row_must_save_before_routing(self):
        with self.assertRaisesRegex(RuntimeError,'guardado de las filas marcadas'):
            self.run_fixture(faultclass='RFN-70',problem='OTROS-01',cause='OTROS-02',remedy='OTROS-03',
                extraFailureRows=[{'type':'CAUSE','code':'OLD-C','suppressed':True}],saveUnavailable=True)
        state=self.browser.execute_script('return state')
        self.assertEqual(state['routes'],0)
        self.assertFalse(any(event[0]=='start' for event in state['events']))

    def test_preexisting_route_saves_and_verifies_marked_extra_row_without_reselecting(self):
        self.run_fixture(faultclass='RFN-70',problem='OTROS-01',cause='OTROS-02',remedy='OTROS-03',
            extraFailureRows=[{'type':'CAUSE','code':'OLD-C','suppressed':True}])
        state=self.browser.execute_script('return state')
        self.assertEqual(state['extraFailureRows'],[])
        self.assertEqual([event for event in state['events'] if event[0]=='select'],[])
        self.assertEqual(state['events'].count(['save']),1)
        self.assertEqual(state['events'].count(['start']),1)

    def test_navigating_to_another_ot_stops_before_editing_any_codes(self):
        self.browser.execute_script("resetState({ot:'9999999'})")
        starter = FixtureStarter(self.browser, '4314531', timeout=0.2)
        with self.assertRaisesRegex(RuntimeError, 'carga de la OT'):
            starter.run()
        self.assertEqual(self.browser.execute_script('return state.events'), [])

    def test_a_closed_workorder_cannot_be_changed(self):
        with self.assertRaisesRegex(RuntimeError, 'CLOSE'):
            self.run_fixture(status='CLOSE')
        self.assertEqual(self.browser.execute_script('return state.events'), [])

    def test_an_unknown_warning_is_not_accepted(self):
        with self.assertRaisesRegex(RuntimeError, 'Error inesperado'):
            self.run_fixture(unexpected=True)
        state = self.browser.execute_script('return state')
        self.assertNotIn(['unsafe-accept'], state['events'])
        self.assertEqual(state['status'], 'APPR')
        self.assertEqual(state['routes'], 1)

    def test_browser_button_only_starts_after_an_explicit_click(self):
        self.browser._maximo_workorder_start_mode = 'configured'
        self.browser._maximo_workorder_start_selection = {
            'class_key':'TRANSPORTES|RFN-70','option_keys':['PROBLEM:OTROS-01','CAUSE:OTROS-02','REMEDY:OTROS-03']}
        with self.maximo_page_scripts():
            self.assertIsNone(workflow.poll_browser_start(self.browser))
            self.assertEqual(self.browser.execute_script('return state.events'), [])
            self.browser.find_element(By.ID, 'maximo-desktop-start-ot').click()
            with patch.object(workflow, 'start_workorder', return_value={'already_started': False,'status':'INPRG'}) as start:
                result = workflow.poll_browser_start(self.browser)
        self.assertEqual(result['status'], 'INPRG')
        self.assertEqual(start.call_args.kwargs['anomaly_mode'], 'configured')
        self.assertEqual(start.call_args.kwargs['anomaly_selection'], self.browser._maximo_workorder_start_selection)
        self.assertEqual(self.browser.execute_script('return state.events'), [])

    def test_manual_only_override_does_not_persist_or_replace_the_default(self):
        default={'class_key':'TRANSPORTES|RFN-70','option_keys':['PROBLEM:OTROS-01','CAUSE:OTROS-02','REMEDY:OTROS-03']}
        self.browser._maximo_workorder_start_mode='configured'
        self.browser._maximo_workorder_start_selection=default.copy()
        with self.maximo_page_scripts():
            workflow.poll_browser_start(self.browser)
            self.browser.find_element(By.ID,'maximo-desktop-start-options').click()
            self.browser.find_element(By.CSS_SELECTOR,'input[name="maximo-start-mode"][value="only"]').click()
            self.browser.find_element(By.XPATH,"//*[@id='maximo-start-options-overlay']//button[normalize-space()='Iniciar OT']").click()
            with patch.object(workflow,'start_workorder',return_value={'already_started':False,'status':'INPRG'}) as start:
                result=workflow.poll_browser_start(self.browser)
        self.assertEqual(result['status'],'INPRG')
        self.assertEqual(start.call_args.kwargs['anomaly_mode'],'only')
        self.assertIsNone(start.call_args.kwargs['anomaly_selection'])
        self.assertEqual(self.browser._maximo_workorder_start_mode,'configured')
        self.assertEqual(self.browser._maximo_workorder_start_selection,default)

    def test_manual_anomaly_dropdowns_return_after_switching_modes(self):
        self.browser._maximo_workorder_start_mode = 'configured'
        self.browser._maximo_workorder_start_selection = workflow.default_selection()
        with self.maximo_page_scripts():
            workflow.poll_browser_start(self.browser)
            self.browser.find_element(By.ID, 'maximo-desktop-start-options').click()
            original_selects = self.browser.find_elements(By.CSS_SELECTOR, '#maximo-start-options-overlay select')
            for _ in range(2):
                self.browser.find_element(By.CSS_SELECTOR, 'input[name="maximo-start-mode"][value="only"]').click()
                self.assertFalse(any(select.is_displayed() for select in self.browser.find_elements(
                    By.CSS_SELECTOR, '#maximo-start-options-overlay select')))
                self.browser.find_element(By.CSS_SELECTOR, 'input[name="maximo-start-mode"][value="configured"]').click()
                selects = self.browser.find_elements(By.CSS_SELECTOR, '#maximo-start-options-overlay select')
                self.assertEqual(len(selects), 4)
                self.assertTrue(all(select.is_displayed() for select in selects))
                self.assertEqual(selects, original_selects)
            confirm = self.browser.find_element(By.XPATH,
                "//*[@id='maximo-start-options-overlay']//button[normalize-space()='Iniciar OT']")
            self.assertTrue(confirm.is_enabled())
            self.browser.execute_script("arguments[0].selectedIndex=0;arguments[0].dispatchEvent(new Event('change'))", selects[0])
            self.assertFalse(confirm.is_enabled())
            self.browser.find_element(By.CSS_SELECTOR, 'input[name="maximo-start-mode"][value="only"]').click()
            self.assertTrue(confirm.is_enabled())
            self.browser.find_element(By.CSS_SELECTOR, 'input[name="maximo-start-mode"][value="configured"]').click()
            self.assertFalse(confirm.is_enabled())
            self.browser.find_element(By.XPATH,
                "//*[@id='maximo-start-options-overlay']//button[normalize-space()='Cancelar']").click()
        self.assertEqual(self.browser.execute_script('return state.events'), [])

    def anomaly_selection(self, remedy='OTROS-04'):
        selection = workflow.default_selection()
        if remedy != 'OTROS-03':
            from failure_catalog import choices
            selection['option_keys'][-1] = next(item['key'] for item in choices(
                selection['class_key'], selection['option_keys'][:-1]) if item['code'] == remedy)
        return selection

    def test_change_anomalies_saves_the_path_without_routing_or_changing_status(self):
        self.browser.execute_script("resetState({status:'INPRG'});render('solutions')")
        changer = FixtureAnomalyChanger(self.browser, '4314531', timeout=5)
        with patch.object(changer, 'route', side_effect=AssertionError('must not route')):
            result = changer.run_change(self.anomaly_selection(), return_tab='Soluciones')
        state = self.browser.execute_script('return state')
        self.assertEqual(result, {'ot':'4314531', 'status':'INPRG', 'action':'change_anomalies'})
        self.assertEqual((state['faultclass'],state['problem'],state['cause'],state['remedy']),
                         ('RFN-70','OTROS-01','OTROS-02','OTROS-04'))
        self.assertFalse(state['dirty'])
        self.assertEqual(state['routes'], 0)
        self.assertNotIn(['start'], state['events'])
        self.assertEqual(self.browser.execute_script('return tab'), 'solutions')

    def test_change_anomalies_keeps_an_already_correct_combination(self):
        self.browser.execute_script("resetState({status:'INPRG',faultclass:'RFN-70',problem:'OTROS-01',cause:'OTROS-02',remedy:'OTROS-03'})")
        FixtureAnomalyChanger(self.browser, '4314531', timeout=5).run_change(workflow.default_selection())
        self.assertEqual(self.browser.execute_script('return state.events'), [])
        self.assertEqual(self.browser.execute_script('return state.status'), 'INPRG')

    def test_change_anomalies_rejects_ineligible_status_and_invalid_selection_before_writes(self):
        for status in ('APPR', 'ISSUE', 'CLOSE', 'CAN'):
            self.browser.execute_script('resetState({status:arguments[0]})', status)
            with self.subTest(status=status), self.assertRaisesRegex(RuntimeError, 'INPRG'):
                FixtureAnomalyChanger(self.browser, '4314531', timeout=1).run_change(workflow.default_selection())
            self.assertEqual(self.browser.execute_script('return state.events'), [])
        self.browser.execute_script("resetState({status:'INPRG'})")
        for spec in ({}, None):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                FixtureAnomalyChanger(self.browser, '4314531', timeout=1).run_change(spec)
            self.assertEqual(self.browser.execute_script('return state.events'), [])

    def test_change_anomalies_stops_if_status_changes_during_save(self):
        self.browser.execute_script("resetState({status:'INPRG'})")
        changer = FixtureAnomalyChanger(self.browser, '4314531', timeout=2)
        original_save = changer.save
        def changed_status():
            result = original_save()
            self.browser.execute_script("state.status='ISSUE';render(tab)")
            return result
        with patch.object(changer, 'save', side_effect=changed_status), self.assertRaisesRegex(RuntimeError, 'INPRG'):
            changer.run_change(self.anomaly_selection())
        state = self.browser.execute_script('return state')
        self.assertEqual(state['routes'], 0)
        self.assertFalse(any(event[0] == 'native-click' for event in state['events']))

    def test_failed_anomaly_change_keeps_diagnostic_evidence_and_never_routes(self):
        self.browser.execute_script("resetState({status:'INPRG',faultclass:'RFN-70',forceNativeError:true})")
        changer = FixtureAnomalyChanger(self.browser, '4314531', timeout=2)
        with patch.object(workflow,'WorkorderAnomalyChanger',return_value=changer), \
             patch.object(workflow,'record_anomaly_incident') as record:
            with self.assertRaisesRegex(RuntimeError,'BMXAA4523E'):
                workflow.change_workorder_anomalies(self.browser,'4314531',self.anomaly_selection())
        self.assertEqual(record.call_args.args[0]['operation'], 'cambio de anomalías')
        self.assertTrue(record.call_args.args[1])
        self.assertEqual(self.browser.execute_script('return state.routes'), 0)

    def test_change_anomalies_button_is_visible_only_for_in_progress_workorders(self):
        with self.maximo_page_scripts():
            for status in ('APPR','INPRG','ISSUE','CLOSE'):
                self.browser.execute_script('resetState({status:arguments[0]})', status)
                workflow.poll_browser_start(self.browser)
                self.assertEqual(self.browser.find_element(By.ID,'maximo-desktop-change-anomalies').is_displayed(), status=='INPRG')
                self.assertEqual(self.browser.find_element(By.ID,'maximo-desktop-start-ot').is_displayed(), status=='APPR')

    def test_change_dialog_cancel_is_read_only_and_confirm_uses_change_action(self):
        default = self.anomaly_selection()
        self.browser._maximo_workorder_start_selection = default.copy()
        self.browser._maximo_workorder_start_mode = 'only'
        self.browser.execute_script("resetState({status:'INPRG'})")
        with self.maximo_page_scripts():
            workflow.poll_browser_start(self.browser)
            self.browser.find_element(By.ID, 'maximo-desktop-change-anomalies').click()
            self.assertFalse(self.browser.find_element(By.CSS_SELECTOR, 'input[value="only"]').is_displayed())
            self.browser.find_element(By.XPATH, "//*[@id='maximo-start-options-overlay']//button[normalize-space()='Cancelar']").click()
            self.assertIsNone(workflow.poll_browser_start(self.browser))
            self.assertEqual(self.browser.execute_script('return state.events'), [])
            self.browser.find_element(By.ID, 'maximo-desktop-change-anomalies').click()
            self.browser.find_element(By.XPATH, "//*[@id='maximo-start-options-overlay']//button[normalize-space()='Guardar anomalías']").click()
            with patch.object(workflow, 'change_workorder_anomalies', return_value={'action':'change_anomalies'}) as change, \
                 patch.object(workflow, 'start_workorder') as start:
                self.assertIsNone(workflow.poll_browser_start(self.browser))
            start.assert_not_called()
            self.assertEqual(change.call_args.args[2], default)
            self.assertEqual(self.browser._maximo_workorder_start_selection, default)
            self.assertNotEqual(self.browser.execute_script('return document.documentElement.dataset.maximoAnomalyChangeBusy'), 'true')

    def test_change_dialog_rejects_a_status_change_before_confirmation(self):
        self.browser.execute_script("resetState({status:'INPRG'})")
        self.browser._maximo_workorder_start_selection = workflow.default_selection()
        with self.maximo_page_scripts():
            workflow.poll_browser_start(self.browser)
            self.browser.find_element(By.ID, 'maximo-desktop-change-anomalies').click()
            self.browser.execute_script("state.status='ISSUE';document.querySelectorAll('label[for]').forEach(l=>{if(l.textContent.trim()==='Estado:')document.getElementById(l.htmlFor).value='ISSUE'})")
            self.browser.find_element(By.XPATH, "//*[@id='maximo-start-options-overlay']//button[normalize-space()='Guardar anomalías']").click()
            self.assertIn('INPRG', self.browser.find_element(By.ID, 'maximo-start-options-error').text)
            with patch.object(workflow,'change_workorder_anomalies') as change:
                self.assertIsNone(workflow.poll_browser_start(self.browser))
            change.assert_not_called()
        self.assertEqual(self.browser.execute_script('return state.events'), [])

    def test_change_and_close_actions_cannot_be_started_together(self):
        from workorder_close import BROWSER_BUTTON_SCRIPT
        close_script = BROWSER_BUTTON_SCRIPT.replace(
            "if (location.origin !== 'https://eam.indraweb.net' || !location.pathname.startsWith('/maximo/ui')) return null;", '')
        self.browser.execute_script("resetState({status:'INPRG'})")
        self.browser._maximo_workorder_start_selection = workflow.default_selection()
        with self.maximo_page_scripts():
            workflow.poll_browser_start(self.browser)
            self.browser.execute_script(close_script)
            close = self.browser.find_element(By.ID, 'maximo-desktop-close-ot')
            self.browser.find_element(By.ID, 'maximo-desktop-change-anomalies').click()
            self.browser.execute_script(close_script)
            self.assertFalse(close.is_enabled())
            self.browser.find_element(By.XPATH, "//*[@id='maximo-start-options-overlay']//button[normalize-space()='Guardar anomalías']").click()
            self.browser.execute_script(close_script)
            self.assertFalse(close.is_enabled())
            self.browser.execute_script("globalThis.MaximoDesktopStartOptions.complete('guardado');arguments[0].dataset.busy='true'", close)
            workflow.poll_browser_start(self.browser)
            self.assertFalse(self.browser.find_element(By.ID, 'maximo-desktop-change-anomalies').is_enabled())
