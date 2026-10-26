"""Tests of explicit start semantics and the Maximo asynchronous workflow."""
import os
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

    def run_fixture(self, **state):
        self.browser.execute_script('resetState(arguments[0])', state)
        return FixtureStarter(self.browser, '4314531', timeout=5).run()

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
                self.assertEqual(state['events'].count(['save']), 2)
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
        self.assertEqual(events.count(['save']), 1)

    def test_bmxaa4523e_is_reported_immediately_without_accepting_or_routing(self):
        with self.assertRaisesRegex(RuntimeError, 'BMXAA4523E'):
            self.run_fixture(faultclass='RFN-70', forceNativeError=True)
        state = self.browser.execute_script('return state')
        self.assertEqual(state['routes'], 0)
        self.assertEqual(len(self.browser.find_elements(By.ID, 'warndiv')), 1)
        self.assertEqual(FixtureStarter(self.browser, '4314531').dialog_snapshot()[-1]['id'], 'warndiv')

    def test_missing_or_wrong_native_code_stops_before_routing(self):
        for state in ({'nativeMissingCode':'OTROS-03'}, {'nativeWrongType':'UNKNOWN'}):
            with self.subTest(state=state), self.assertRaisesRegex(RuntimeError, 'opción|nivel'):
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
        with self.assertRaisesRegex(RuntimeError, 'sin confirmar OTROS-01'):
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
        def execute(script, *args):
            return original(script.replace("if (location.origin !== 'https://eam.indraweb.net' || !location.pathname.startsWith('/maximo/ui')) return '';", ''), *args)
        with patch.object(self.browser, 'execute_script', side_effect=execute):
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
        with patch.object(workflow, 'WorkorderStarter', FixtureStarter):
            # The injection intentionally targets Maximo only; use the same
            # injected DOM on a mocked Maximo location for this fixture alone.
            original = self.browser.execute_script
            def execute(script, *args):
                script = script.replace("if (location.origin !== 'https://eam.indraweb.net' || !location.pathname.startsWith('/maximo/ui')) return '';", '')
                return original(script, *args)
            with patch.object(self.browser, 'execute_script', side_effect=execute):
                self.assertIsNone(workflow.poll_browser_start(self.browser))
                self.assertEqual(original('return state.events'), [])
                self.browser.find_element(By.ID, 'maximo-desktop-start-ot').click()
                result = workflow.poll_browser_start(self.browser)
            self.assertEqual(result['status'], 'INPRG')
            self.assertEqual(original('return state.events').count(['start']), 1)
