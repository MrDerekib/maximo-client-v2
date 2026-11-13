"""MD repairs commit through native routing; never save each preparation step."""
import tests
import os
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from failure_catalog import default_selection,resolve_selection
from technician_repair import RepairPreparer,RepairCloser,RepairEntry,reviewed_repair,run_repair
from warehouse import WarehouseItem
from warehouse_recovery import RecoveryStore
from tests.test_support import temporary_directory
from tests.test_workorder_close import FIXTURE


class RepairDraftTests(TestCase):
    def test_new_anomalies_are_validated_without_save_or_reload(self):
        p=RepairPreparer(Mock(),'1','INPRG')
        p.require_approved=Mock();p.tab=Mock();p.failure_rows=Mock(return_value=[])
        p.value=Mock(return_value='RFN-70')
        p.verify_failure_rows=Mock();p.verify_solution_codes=Mock()
        p.save=Mock(side_effect=AssertionError('No Save'))
        p.reload_workorder=Mock(side_effect=AssertionError('No reload'))
        path=resolve_selection(default_selection())['path']
        self.assertTrue(p.save_anomalies(path,'RFN-70'))
        p.verify_failure_rows.assert_called_once_with(path)
        p.verify_solution_codes.assert_called_once_with(path)
        p.save.assert_not_called();p.reload_workorder.assert_not_called()

    def test_native_hierarchy_deletion_keeps_its_required_commit(self):
        p=RepairPreparer(Mock(),'1','APPR')
        p.require_approved=Mock();p.tab=Mock()
        p.failure_rows=Mock(return_value=[{'toggleTitle':'Deshacer suprimir'}])
        with patch('workorder_start.WorkorderStarter.save_anomalies',return_value=True) as commit:
            self.assertTrue(p.save_anomalies([]))
        commit.assert_called_once_with([],None)

    def test_exact_existing_note_is_not_changed_and_conflicting_details_stop(self):
        p=RepairPreparer(Mock(),'1','INPRG')
        p.open_entry=Mock(return_value=True);p.details=Mock(return_value='Resultado')
        p.ensure_incident=Mock();p.save=Mock()
        p.ensure_entry(RepairEntry('Test','Resultado'))
        with self.assertRaisesRegex(RuntimeError,'otros detalles'):
            p.ensure_entry(RepairEntry('Test',''))
        p.ensure_incident.assert_not_called();p.save.assert_not_called()


class FixturePreparer(RepairPreparer):
    def check_location(self):
        if self.driver.current_url!=FIXTURE:raise AssertionError('Offline only')
    def response_sequence(self):return self.driver.execute_script('return state.responses')
    def failure_rows(self):
        return self.driver.execute_script("return [['PROBLEM','problem'],['CAUSE','cause'],['REMEDY','remedy']].filter(([kind,key])=>state[key]).map(([kind,key])=>({type:kind,code:state[key],toggleTitle:''}))")


class FixtureRepairCloser(RepairCloser):
    route_dialog_timeout=.3
    def check_location(self):
        if self.driver.current_url!=FIXTURE:raise AssertionError('Offline only')
    def response_sequence(self):return self.driver.execute_script('return state.responses')
    def reload_workorder(self):
        # A single final server read is allowed, never while drafts are pending.
        if self.driver.execute_script("return state.status==='INPRG'"):
            raise AssertionError('MD discarded preparation drafts before routing')
        self.session.readbacks+=1
        if self.session.drop_entries:
            self.driver.execute_script('state.logs=[];persist()')
        self.driver.refresh()


class FixtureSession:
    def __init__(self,driver):
        self.driver=driver;self.reader=None;self.readbacks=0;self.closed=False;self.drop_entries=False
    def open(self,ot):return self.driver.execute_script('return state.status')
    def identity(self):return {'Activo':'A','Nº de serie':'S','Planta':'LAB-BAD'}
    def check(self,state,identity):
        if self.reader.value('Estado')!=state or identity!=self.identity():
            raise RuntimeError('State/identity mismatch')
    def history_count(self,caption):
        event='confirm-discard' if caption=='Desechar equipo' else 'confirm-close'
        return self.driver.execute_script('return state.events.filter(e=>e[0]===arguments[0]).length',event)
    def close(self):self.closed=True
    def diagnostic_context(self):return {'fixture':True}


@skipUnless(os.environ.get('MAXIMO_BROWSER_TESTS')=='1','Offline Edge tests are opt-in')
class RepairInPlaceBrowserTests(TestCase):
    @classmethod
    def setUpClass(cls):
        options=Options();options.add_argument('--headless=new')
        cls.browser=webdriver.Edge(options=options)
    @classmethod
    def tearDownClass(cls):cls.browser.quit()
    def plan(self,action):
        return reviewed_repair(WarehouseItem('4378677',serial='S'),
            {'reference':'stock','entries':[{'summary':'Prueba','details':'Correcta'},
             {'summary':'Inspección','details':'Sin daños'}],'duration':'1',
             'time_mode':'end','time':'2026-10-26T11:00:00','action':action,
             'justification':'Irreparable' if action=='discard' else ''},default_selection())

    def test_full_md_repairs_from_appr_and_inprg_never_save_preparation(self):
        for state,action,expected in [('INPRG','close','ISSUE'),('APPR','close','ISSUE'),('INPRG','discard','CLOSE')]:
            with self.subTest(state=state,action=action),temporary_directory() as folder:
                self.browser.get(FIXTURE)
                self.browser.execute_script("resetState({status:arguments[0],logs:[],duration:'',end:'',resultStatus:arguments[1]})",state,expected)
                session=FixtureSession(self.browser)
                with patch('technician_repair.RepairPreparer',FixturePreparer),patch('technician_repair.RepairCloser',FixtureRepairCloser),patch.object(FixturePreparer,'save',side_effect=AssertionError('No intermediate Save')),patch.object(FixtureRepairCloser,'save',side_effect=AssertionError('No closing Save')):
                    result=run_repair(self.plan(action),session_factory=lambda:session,store=RecoveryStore(Path(folder)))
                self.assertEqual(result['status'],expected)
                data=self.browser.execute_script('return state')
                self.assertFalse(any(e[0] in ('save','save-rejected') for e in data['events']))
                self.assertEqual(sum(e[0]=='confirm-start' for e in data['events']),int(state=='APPR'))
                self.assertEqual(sum(e[0]=='confirm-'+action for e in data['events']),1)
                self.assertEqual([r['summary'] for r in data['logs']],['inc: stock','Prueba','Inspección'])
                self.assertEqual(data['duration'],'1');self.assertEqual(data['end'],'2026-10-26T11:00:00')
                self.assertEqual(session.readbacks,1);self.assertTrue(session.closed)

    def test_missing_committed_worklog_stops_without_repeating_route(self):
        self.browser.get(FIXTURE)
        self.browser.execute_script("resetState({logs:[],duration:'',end:''})")
        session=FixtureSession(self.browser);session.drop_entries=True
        with temporary_directory() as folder,patch('technician_repair.RepairPreparer',FixturePreparer),patch('technician_repair.RepairCloser',FixtureRepairCloser):
            store=RecoveryStore(Path(folder))
            with self.assertLogs(level='ERROR'),self.assertRaisesRegex(RuntimeError,'no se confirmó todo el Registro'):
                run_repair(self.plan('close'),session_factory=lambda:session,store=store)
            self.assertTrue(store.get('4378677')['confirmation_attempted'])
            self.assertNotEqual(store.get('4378677')['phase'],'verified')
        self.assertEqual(self.browser.execute_script("return state.events.filter(e=>e[0]==='confirm-close').length"),1)
        self.assertTrue(session.closed)
