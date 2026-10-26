"""Tests of explicit start semantics and the Maximo asynchronous workflow."""
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options

import config
import db
import maximo_client as client
import workorder_start as workflow
from tests.test_support import temporary_directory


class StartConfigurationTests(TestCase):
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

    def test_disabled_start_does_not_launch_a_browser(self):
        with patch.object(client, 'load_config', return_value=config.AppConfig()), \
             patch.object(client, 'setup_driver') as setup:
            with self.assertRaisesRegex(ValueError, 'habilitado'):
                client.start_ot('4314531')
        setup.assert_not_called()

    def test_explicit_headless_start_reports_result_and_always_closes_its_session(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                driver, report = Mock(), Mock()
                cfg = SimpleNamespace(workorder_start_enabled=True, repair_extension_enabled=False)
                result = {'ot':'4314531','status':'INPRG','already_started':False}
                with patch.object(client, 'load_config', return_value=cfg), \
                     patch.object(client, 'create_edge_profile', return_value='test-profile'), \
                     patch.object(client, 'setup_driver', return_value=driver) as setup, \
                     patch.object(client, 'login'), patch.object(client, 'open_workorders_app'), \
                     patch.object(client, 'wait_for'), \
                     patch.object(client, 'cleanup_edge_profile') as cleanup, \
                     patch.object(workflow, 'start_workorder', side_effect=RuntimeError('fallo') if failure else None,
                                  return_value=result) as start:
                    if failure:
                        with self.assertRaisesRegex(RuntimeError, 'fallo'):
                            client.start_ot('4314531', report)
                    else:
                        self.assertEqual(client.start_ot('4314531', report), result)
                self.assertTrue(setup.call_args.kwargs['headless'])
                start.assert_called_once_with(driver, '4314531', report)
                driver.quit.assert_called_once()
                cleanup.assert_called_once_with('test-profile')

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

    def test_an_in_progress_workorder_is_not_edited_or_routed_again(self):
        result = self.run_fixture(status='INPRG')
        self.assertTrue(result['already_started'])
        self.assertEqual(self.browser.execute_script('return state.events'), [])

    def test_preexisting_correct_codes_are_kept_and_the_order_is_started_once(self):
        self.run_fixture(faultclass='RFN-70', problem='OTROS-01', cause='OTROS-02', remedy='OTROS-03')
        events = self.browser.execute_script('return state.events')
        self.assertFalse(any(event[0]=='select' for event in events))
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
