import tests
import os
import time
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from browser_close_records import summarize_records, validate_record_approval, prepare_browser_records, BrowserRecordReader
import workorder_close as workflow
from tests.test_workorder_close import FixtureCloser, FIXTURE

ANOMALIES={'class':'RFN-70','codes':{'PROBLEM':'OTROS-01','CAUSE':'OTROS-02','REMEDY':'OTROS-03'},'complete':True}
def entry(summary,details='',kind='CLIENTNOTE'):
    return {'summary':summary,'details':details,'type':kind,'author':'TECH','date':'2026-10-26'}
def records(*entries,complete=True):
    return summarize_records({'complete':complete,'entries':list(entries),'error':''})

class BrowserRecordValidationTests(TestCase):
    def test_system_notes_and_incident_only_are_not_repair_activity(self):
        data=records(entry('inc: stock'),entry('Inicio de OT',kind='SYSTEM'),entry('inc:'))
        self.assertEqual(data['references'],['inc: stock']);self.assertEqual(data['notes'],[])
        with self.assertRaisesRegex(ValueError,'trabajos'):
            validate_record_approval({'reference':'stock','activity_confirmed':True},data,ANOMALIES)

    def test_existing_notes_require_review_but_are_never_rewritten(self):
        data=records(entry('inc: sin inc'),entry('Test equipo','Aviso'))
        with self.assertRaises(ValueError):validate_record_approval({'reference':'sin inc'},data,ANOMALIES)
        reference,additions=validate_record_approval({'reference':'sin inc','activity_confirmed':True},data,ANOMALIES)
        self.assertEqual(reference,'inc: sin inc');self.assertEqual(additions,[])

    def test_free_incident_new_notes_and_exact_retries(self):
        request={'reference':'INC: stock Ávila','entries':[{'summary':'Prueba','details':'Equipo comprobado'}]}
        ref,additions=validate_record_approval(request,records(),ANOMALIES)
        self.assertEqual(ref,'inc: stock Ávila');self.assertEqual(len(additions),1)
        _,additions=validate_record_approval(request,records(entry(ref),entry('Prueba','Equipo comprobado')),ANOMALIES)
        self.assertEqual(additions,[])

    def test_new_incident_and_conflicting_details_need_explicit_handling(self):
        data=records(entry('inc: 111'),entry('Prueba','Resultado original'))
        with self.assertRaisesRegex(ValueError,'otra incidencia'):
            validate_record_approval({'reference':'222','activity_confirmed':True},data,ANOMALIES)
        with self.assertRaisesRegex(ValueError,'otros detalles'):
            validate_record_approval({'reference':'111','entries':[{'summary':'Prueba','details':'Otro resultado'}]},data,ANOMALIES)

    def test_incomplete_reads_anomalies_and_bad_entries_stop(self):
        for data,anomalies,request in [
            (records(complete=False),ANOMALIES,{'reference':'stock'}),
            (records(),{'complete':False},{'reference':'stock'}),
            (records(),ANOMALIES,{'reference':'stock','entries':[{'details':'No summary'}]}),
            (records(),ANOMALIES,{'reference':'stock','entries':[{'summary':'inc: 12'}]}),
        ]:
            with self.subTest(request=request),self.assertRaises(ValueError):validate_record_approval(request,data,anomalies)

    def test_browser_readback_uses_same_session_native_navigation_and_keeps_window_visible(self):
        closer=workflow.WorkorderCloser(Mock(),'4411048')
        closer._browser_native_navigation=True
        closer.check_location=Mock();closer.idle=Mock();closer.check_ot=Mock();closer.reject_dialogs=Mock()
        with patch('maximo_client.open_workorders_app') as navigate,patch('maximo_client.read_workorder_status',return_value='INPRG') as read:
            closer.reload_workorder()
        navigate.assert_called_once_with(closer.driver,headless=False)
        read.assert_called_once_with(closer.driver,'4411048')
        closer.driver.refresh.assert_not_called()
        closer.driver.set_window_position.assert_not_called()

    def test_summary_validation_waits_for_server_ack_before_any_save(self):
        reader=BrowserRecordReader(Mock())
        reader.response_sequence=Mock(return_value=10)
        reader.idle=Mock();reader.require_approved=Mock();reader.save=Mock()
        reader.dialogs=Mock(return_value=[])
        reader.value=Mock(return_value='Prueba de guardado')
        def wait(predicate,description):
            self.assertIn('validar Resumen',description)
            self.assertFalse(predicate(None))
            reader.response_sequence.return_value=11
            self.assertTrue(predicate(None))
        reader.wait=Mock(side_effect=wait)
        with patch('technician_sat.TechnicianSatPreparer._write_text') as write:
            reader._write_text('Resumen','Prueba de guardado')
        write.assert_called_once_with('Resumen','Prueba de guardado',None)
        reader.save.assert_not_called()

    def test_changed_server_records_stop_before_creating_entries(self):
        closer=Mock();closer.save_action_state.return_value={'control':None}
        snapshot={'ot':'1','duration':'1','start':'2026-10-26T10:00:00','end':'2026-10-26T11:00:00'}
        closer.inspect_repair.return_value=snapshot
        pending={'snapshot':snapshot,'records':records(entry('inc: stock'),entry('Prueba','Original')),'anomalies':ANOMALIES}
        with patch('browser_close_records.BrowserRecordReader') as reader:
            reader.return_value.read_records.return_value=records(entry('inc: stock'),entry('Prueba','Cambiado'))
            with self.assertRaisesRegex(RuntimeError,'cambiaron'):
                prepare_browser_records(closer,{'reference':'stock','activity_confirmed':True},pending)
            reader.return_value.ensure_entry.assert_not_called()


@skipUnless(os.environ.get('MAXIMO_BROWSER_TESTS')=='1','Offline Edge tests are opt-in')
class BrowserDynamicCloseTests(TestCase):
    @classmethod
    def setUpClass(cls):
        options=Options();options.add_argument('--headless=new');cls.browser=webdriver.Edge(options=options)
    @classmethod
    def tearDownClass(cls):cls.browser.quit()
    def setUp(self):
        self.browser.get(FIXTURE);self.browser.execute_script("resetState({duration:'1',start:'2026-10-26T10:00:00',end:'2026-10-26T11:00:00'})")
        self.browser._maximo_close_review=None
    def poll(self):
        script=workflow.BROWSER_BUTTON_SCRIPT.replace("location.origin !== 'https://eam.indraweb.net' || !location.pathname.startsWith('/maximo/ui')",'location.href !== '+repr(FIXTURE))
        with patch.object(workflow,'BROWSER_BUTTON_SCRIPT',script),patch.object(workflow,'WorkorderCloser',FixtureCloser):
            return workflow.poll_browser_close(self.browser)
    def prepare(self):
        self.poll();self.browser.find_element(By.ID,'maximo-desktop-close-ot').click();self.poll()
        return self.browser.find_element(By.ID,'maximo-close-review')
    def test_complete_review_prefills_reference_dates_and_preserves_exact_seconds(self):
        self.browser.execute_script("resetState({duration:'1',start:'2026-10-26T10:07:16',end:'2026-10-26T11:07:16'})")
        dialog=self.prepare()
        self.assertEqual(dialog.find_element(By.NAME,'reference').get_property('value'),'inc: stock')
        self.assertEqual(dialog.find_element(By.NAME,'start').get_property('value'),'2026-10-26T10:07')
        self.assertTrue(dialog.find_element(By.NAME,'confirm').get_property('disabled'))
        dialog.find_element(By.NAME,'activityAck').click();dialog.find_element(By.NAME,'confirm').click()
        request=self.browser.execute_script('return JSON.parse(document.documentElement.dataset.maximoCloseOtRequest)')
        self.assertEqual(request['start'],'2026-10-26T10:07:16');self.assertEqual(request['end'],'2026-10-26T11:07:16')
        self.assertEqual(self.browser.execute_script('return state.events'),[])

    def test_pagination_reads_all_entries_and_never_creates_or_routes(self):
        self.browser.execute_script("state.pageSize=1;persist()")
        reader=BrowserRecordReader(FixtureCloser(self.browser,'4378677'))
        data=reader.read_records()
        self.assertEqual(len(data['entries']),2)
        self.assertEqual(data['entries'][1]['details'],'Pruebas realizadas')
        self.assertEqual(self.browser.execute_script('return state.events'),[])
        self.assertEqual(self.browser.execute_script('return state.routes'),0)

    def test_missing_records_are_prepared_without_saving_or_reopening(self):
        self.browser.execute_script("state.logs=[];persist();render('main')")
        dialog=self.prepare();self.assertTrue(dialog.find_element(By.NAME,'confirm').get_property('disabled'))
        dialog.find_element(By.NAME,'reference').send_keys('stock Ávila')
        dialog.find_element(By.NAME,'addEntry').click()
        row=dialog.find_element(By.CSS_SELECTOR,'.close-new-entry')
        row.find_element(By.TAG_NAME,'input').send_keys('Test equipo')
        row.find_element(By.TAG_NAME,'textarea').send_keys('Aviso sobretensión')
        self.assertFalse(dialog.find_element(By.NAME,'confirm').get_property('disabled'))
        dialog.find_element(By.NAME,'confirm').click()
        request=self.browser.execute_script('return JSON.parse(document.documentElement.dataset.maximoCloseOtRequest)')
        # Run preparation and verification only; NEVER route in this test.
        pending=self.browser._maximo_close_review;pending['approved']=True
        closer=FixtureCloser(self.browser,'4378677')
        with patch.object(closer,'reload_workorder',side_effect=AssertionError('No reabrir borradores')),patch.object(closer,'save',side_effect=AssertionError('Sin Guardar intermedio')),patch.object(BrowserRecordReader,'save',side_effect=AssertionError('Sin Guardar Registro')):
            closer.prepare_close(request,pending)
        result=self.browser.execute_script('return state')
        self.assertEqual(result['routes'],0)
        self.assertEqual(result['logs'],[])
        self.assertEqual([(row['summary'],row['details']) for row in self.browser.execute_script('return draft.logs')],
                         [('inc: stock Ávila',''),('Test equipo','Aviso sobretensión')])

    def test_complete_local_close_routes_once_without_rewriting_logs_or_times(self):
        dialog=self.prepare()
        dialog.find_element(By.NAME,'activityAck').click();dialog.find_element(By.NAME,'confirm').click()
        with patch.object(FixtureCloser,'reload_workorder',side_effect=AssertionError('No reabrir una ficha confirmada')):
            result=self.poll()
        self.assertEqual(result['status'],'ISSUE')
        events=self.browser.execute_script('return state.events')
        self.assertEqual(sum(event[0]=='confirm-close' for event in events),1)
        self.assertFalse(any(event[0] in ('log-new','log-edit','duration','start','end') for event in events))

    def test_notes_changed_after_review_block_before_writes_or_route(self):
        dialog=self.prepare()
        dialog.find_element(By.NAME,'activityAck').click();dialog.find_element(By.NAME,'confirm').click()
        request=self.browser.execute_script('return JSON.parse(document.documentElement.dataset.maximoCloseOtRequest)')
        pending=self.browser._maximo_close_review;pending['approved']=True
        self.browser.execute_script("state.logs[1].details='Cambio de otro usuario';persist()")
        with self.assertRaisesRegex(RuntimeError,'cambiaron'):
            FixtureCloser(self.browser,'4378677').prepare_close(request,pending)
        self.assertEqual(self.browser.execute_script('return state.events'),[])

    def test_append_on_paginated_registry_preserves_every_existing_note(self):
        self.browser.execute_script("state.pageSize=1;persist()")
        reader=BrowserRecordReader(FixtureCloser(self.browser,'4378677'))
        from technician_repair import RepairEntry
        reader.ensure_entry(RepairEntry('Comprobación final','Resultado correcto'))
        reader.ensure_entry(RepairEntry('Comprobación final','Resultado correcto'))
        logs=self.browser.execute_script('return draft.logs||state.logs')
        self.assertEqual(len(logs),3)
        self.assertEqual(logs[-1]['details'],'Resultado correcto')
        self.assertEqual(self.browser.execute_script("return state.events.filter(event=>event[0]==='log-new').length"),1)
        self.assertEqual(self.browser.execute_script('return state.routes'),0)

    def test_missing_anomalies_never_enable_close(self):
        self.browser.execute_script("state.remedy='';persist()")
        dialog=self.prepare()
        dialog.find_element(By.NAME,'activityAck').click()
        self.assertTrue(dialog.find_element(By.NAME,'confirm').get_property('disabled'))
        self.assertIn('anomalías',dialog.find_element(By.ID,'maximo-close-error').text)
        self.assertEqual(self.browser.execute_script('return state.events'),[])

    def test_async_summary_is_validated_before_the_next_unsaved_entry(self):
        self.browser.execute_script("state.asyncSummaryCommit=true;persist()")
        reader=BrowserRecordReader(FixtureCloser(self.browser,'4378677'))
        from technician_repair import RepairEntry
        with patch.object(reader,'save',side_effect=AssertionError('Sin Guardar')),patch.object(reader,'reload_workorder',side_effect=AssertionError('Sin reconsulta')):
            reader.ensure_entry(RepairEntry('Validación asíncrona',''))
            reader.ensure_entry(RepairEntry('Segundo trabajo','Resultado correcto'))
        events=self.browser.execute_script('return state.events')
        creations=[i for i,event in enumerate(events) if event[0]=='log-new']
        edited=next(i for i,event in enumerate(events) if event[:2]==['log-edit','summary'])
        self.assertLess(edited,creations[1])
        self.assertFalse(any(event[0] in ('save','save-rejected') for event in events))
        self.assertEqual(self.browser.execute_script('return state.routes'),0)

    def test_failed_pagination_blocks_dialog_confirmation(self):
        self.browser.execute_script("state.pageSize=1;persist();render('main')")
        with patch.object(BrowserRecordReader,'page',side_effect=RuntimeError('No se pudo leer la página')):
            dialog=self.prepare()
        self.assertTrue(dialog.find_element(By.NAME,'confirm').get_property('disabled'))
        self.assertIn('Registro completo',dialog.find_element(By.ID,'maximo-close-error').text)
        self.assertEqual(self.browser.execute_script('return state.events'),[])

    def test_multiple_incidents_require_selection_and_do_not_overwrite(self):
        self.browser.execute_script("state.logs.push({summary:'inc: 999',details:'',type:'CLIENTNOTE'});persist();render('main')")
        dialog=self.prepare()
        self.assertEqual(dialog.find_element(By.NAME,'reference').get_property('value'),'')
        dialog.find_element(By.NAME,'reference').send_keys('inc: stock')
        dialog.find_element(By.NAME,'activityAck').click()
        self.assertFalse(dialog.find_element(By.NAME,'confirm').get_property('disabled'))
        self.assertEqual(self.browser.execute_script('return state.events'),[])

    def test_cancel_keeps_notes_dates_and_original_tab_without_writes(self):
        self.poll();self.browser.execute_script("render('records')")
        self.browser.find_element(By.ID,'maximo-desktop-close-ot').click();self.poll()
        self.browser.find_element(By.NAME,'cancel').click();self.poll()
        self.assertEqual(self.browser.execute_script('return tab'),'records')
        self.assertEqual(self.browser.execute_script('return state.events'),[])

    def test_native_pending_changes_can_be_reviewed_without_saving_or_discarding(self):
        self.browser.execute_script("draft.duration='2';state.dirty=true;render('main')")
        self.poll();self.browser.find_element(By.ID,'maximo-desktop-close-ot').click();self.poll()
        self.assertTrue(self.browser.find_elements(By.ID,'maximo-close-review'))
        self.assertEqual(self.browser.find_element(By.NAME,'duration').get_property('value'),'2')
        self.assertEqual(self.browser.execute_script('return draft.duration'),'2')
        self.assertEqual(self.browser.execute_script('return state.events'),[])


    def test_full_browser_close_commits_new_records_through_routing_only(self):
        self.browser.execute_script("state.logs=[];state.duration='';persist();render('main')")
        dialog=self.prepare()
        dialog.find_element(By.NAME,'reference').send_keys('stock Ávila')
        dialog.find_element(By.NAME,'duration').send_keys('1')
        for summary,details in [('Prueba equipo','Resultado correcto'),('Inspección','Sin daños')]:
            dialog.find_element(By.NAME,'addEntry').click()
            row=dialog.find_elements(By.CSS_SELECTOR,'.close-new-entry')[-1]
            row.find_element(By.TAG_NAME,'input').send_keys(summary)
            row.find_element(By.TAG_NAME,'textarea').send_keys(details)
        dialog.find_element(By.NAME,'confirm').click()
        with patch.object(FixtureCloser,'save',side_effect=AssertionError('Sin Guardar antes de enrutar')),patch.object(BrowserRecordReader,'save',side_effect=AssertionError('Sin Guardar Registro')),patch.object(FixtureCloser,'reload_workorder',side_effect=AssertionError('Sin reconsulta')):
            result=self.poll()
        self.assertEqual(result['status'],'ISSUE')
        state=self.browser.execute_script('return state')
        self.assertFalse(any(event[0] in ('save','save-rejected') for event in state['events']))
        self.assertEqual(sum(event[0]=='confirm-close' for event in state['events']),1)
        self.assertEqual([row['summary'] for row in state['logs']],['inc: stock Ávila','Prueba equipo','Inspección'])
        self.assertEqual(state['duration'],'1')
        self.assertEqual(state['end'],'2026-10-26T11:00:00')

    def test_preparation_never_invokes_native_save_even_when_save_would_fail(self):
        self.browser.execute_script("state.forceSaveError=true;persist()")
        reader=BrowserRecordReader(FixtureCloser(self.browser,'4378677'))
        from technician_repair import RepairEntry
        reader.ensure_entry(RepairEntry('Registro pendiente del cierre',''))
        state=self.browser.execute_script('return state')
        self.assertFalse(any(event[0] in ('save','save-rejected') for event in state['events']))
        self.assertEqual(state['routes'],0)
        self.assertFalse(any(row['summary']=='Registro pendiente del cierre' for row in state['logs']))
        self.assertTrue(any(row['summary']=='Registro pendiente del cierre' for row in self.browser.execute_script('return draft.logs')))

    def test_closed_registry_verification_is_read_only_and_detects_missing_work(self):
        from browser_close_records import verify_browser_closed_records
        # Use the fixture's real row metadata for preservation checks.
        closer=FixtureCloser(self.browser,'4378677')
        baseline=summarize_records(BrowserRecordReader(closer).read_records())
        pending={'records':baseline,'expected_reference':'inc: stock','expected_entries':[{'summary':'Trabajo perdido','details':''}]}
        self.browser.execute_script("state.status='ISSUE';persist();render('main')")
        with self.assertRaisesRegex(RuntimeError,'no se confirmaron todos'):
            verify_browser_closed_records(closer,pending,'ISSUE')
        self.assertEqual(self.browser.execute_script('return state.events'),[])
