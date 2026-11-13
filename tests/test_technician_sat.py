import tests
from unittest import TestCase
from unittest.mock import Mock
from failure_catalog import default_selection
from warehouse import WarehouseItem
from technician_sat import reviewed_sat_plans, TECHNICIAN_SAT_LABEL


class TechnicianSatPlanTests(TestCase):
    def values(self):
        return {'1': {'duration': '0,75', 'incident': '12345678', 'reason': 'Motivo de prueba local'}}

    def test_review_freezes_inputs_and_keeps_technician_action_distinct(self):
        values=self.values();selection=default_selection()
        plan,=reviewed_sat_plans([WarehouseItem('1')],values,selection)
        values['1']['incident']='999';selection.clear()
        self.assertEqual(plan.incident_summary,'inc: 12345678')
        self.assertTrue(plan.anomaly_selection)
        self.assertEqual(TECHNICIAN_SAT_LABEL,'Enviar a SAT Externo')
        self.assertNotIn('Confirmar',TECHNICIAN_SAT_LABEL)

    def test_incident_and_reason_are_required_per_ot(self):
        for field in ('incident','reason'):
            values=self.values();values['1'][field]=''
            with self.subTest(field=field),self.assertRaises(ValueError):
                reviewed_sat_plans([WarehouseItem('1')],values,default_selection())

    def test_duration_requires_quarter_hours(self):
        for value in ('','0','0,1','-1','NaN'):
            values=self.values();values['1']['duration']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                reviewed_sat_plans([WarehouseItem('1')],values,default_selection())

    def test_every_ot_must_have_its_own_reviewed_values(self):
        with self.assertRaises(ValueError):
            reviewed_sat_plans([WarehouseItem('1'),WarehouseItem('2')],self.values(),default_selection())

    def test_invalid_anomaly_route_is_rejected_before_any_operation(self):
        with self.assertRaises(ValueError):
            reviewed_sat_plans([WarehouseItem('1')],self.values(),{})


    def test_stock_reference_is_supported_without_changing_it_to_a_number(self):
        values=self.values();values['1']['incident']='stock';values['1']['duration']='0,5'
        plan,=reviewed_sat_plans([WarehouseItem('1')],values,default_selection())
        self.assertEqual(plan.incident_summary,'inc: stock')

    def test_incident_cannot_contain_control_characters(self):
        values=self.values();values['1']['incident']='stock\nextra'
        with self.assertRaises(ValueError):
            reviewed_sat_plans([WarehouseItem('1')],values,default_selection())


    def preparer(self):
        from technician_sat import TechnicianSatPreparer
        preparer=TechnicianSatPreparer(Mock(),'1')
        preparer.require_approved=Mock()
        preparer.reload_workorder=Mock()
        preparer.tab=Mock()
        return preparer

    def test_existing_incident_never_creates_a_second_row(self):
        preparer=self.preparer();preparer.incident_present=Mock(return_value=True)
        self.assertFalse(preparer.ensure_incident('inc: stock'))
        preparer.driver.find_elements.assert_not_called()

    def test_preparation_reloads_and_verifies_without_routing(self):
        preparer=self.preparer()
        preparer.fault_reason=Mock(return_value='No admite')
        preparer.apply_anomalies=Mock(return_value={'path':[]})
        preparer.set_repair_duration=Mock();preparer.ensure_incident=Mock(return_value=True)
        preparer.save=Mock(return_value=True);preparer.wait=Mock()
        preparer.value=Mock(return_value='0,50');preparer.incident_present=Mock(return_value=True)
        preparer.verify_failure_rows=Mock();preparer.verify_solution_codes=Mock();preparer.route=Mock()
        plan,=reviewed_sat_plans([WarehouseItem('1')],self.values(),default_selection())
        preparer.value.side_effect=lambda caption:'RFN-70' if caption=='Clase de anomalía' else '0,75'
        result=preparer.prepare(plan)
        self.assertTrue(result['prepared']);self.assertEqual(result['status'],'APPR')
        preparer.reload_workorder.assert_called_once();preparer.driver.refresh.assert_not_called();preparer.route.assert_not_called()
        preparer.driver.find_element.assert_not_called()
        preparer.verify_failure_rows.assert_called_once()

    def test_saved_duration_mismatch_prevents_any_route(self):
        preparer=self.preparer()
        preparer.fault_reason=Mock(return_value='No admite');preparer.apply_anomalies=Mock(return_value={'path':[]})
        preparer.set_repair_duration=Mock();preparer.ensure_incident=Mock();preparer.save=Mock(return_value=True)
        preparer.wait=Mock();preparer.value=Mock(return_value='0,25');preparer.route=Mock()
        plan,=reviewed_sat_plans([WarehouseItem('1')],self.values(),default_selection())
        with self.assertRaises(RuntimeError):preparer.prepare(plan)
        preparer.route.assert_not_called()

    def test_worklog_partial_page_does_not_create_potential_duplicate(self):
        preparer=self.preparer();preparer.worklog_snapshot=Mock(return_value={'rows':[], 'totals':[20]})
        with self.assertRaises(RuntimeError):preparer.ensure_incident('inc: stock')
        preparer.driver.find_elements.assert_not_called()


    def test_save_action_snapshot_retries_only_the_stale_read(self):
        from workorder_start import WorkorderStarter
        from selenium.common.exceptions import StaleElementReferenceException
        preparer=WorkorderStarter(Mock(),'1',timeout=1)
        preparer._save_action_state=Mock(side_effect=[StaleElementReferenceException('redrawn'),
            {'control':None,'unavailable':'disabled'}])
        self.assertEqual(preparer.save_action_state()['unavailable'],'disabled')
        self.assertEqual(preparer._save_action_state.call_count,2)
        preparer.driver.find_element.assert_not_called()

    def test_technical_run_needs_reviewed_plans_before_any_session(self):
        from warehouse_transport import run_live
        factory=Mock()
        with self.assertRaises(ValueError):
            run_live([WarehouseItem('1')],'technician_sat_external',session_factory=factory)
        factory.assert_not_called()

    def test_technical_defaults_only_reads_and_closes_the_session(self):
        from technician_sat import technician_sat_defaults
        session=Mock();session.open.return_value='APPR'
        session.identity.return_value={'Activo':'A','Planta':'LAB-BAD','Nº de serie':'S'}
        session.reader.value.side_effect=['NO ADMITE','0,50']
        data=technician_sat_defaults([WarehouseItem('1',serial='S')],session_factory=lambda:session)
        self.assertEqual(data['1'],{'reason':'NO ADMITE','duration':'0,50','status':'APPR'})
        session.close.assert_called_once()
        session.driver.find_element.assert_not_called()

    def test_technical_run_prepares_under_durable_claim_and_routes_once(self):
        from pathlib import Path
        from unittest.mock import patch
        from tests.test_support import temporary_directory
        from tests.test_warehouse_recovery import FakeServer
        from warehouse_recovery import RecoveryStore
        from warehouse_transport import run_live
        server=FakeServer(action='technician_sat_external',states={'1':'APPR'})
        original=server.session
        def factory():
            session=original()
            session.accept_button.return_value.click.side_effect=lambda:server.sent.update(['1'])
            return session
        plan,=reviewed_sat_plans([WarehouseItem('1')],self.values(),default_selection())
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder))
            def prepare(p):
                self.assertEqual(store.get('1')['phase'],'preparing')
                self.assertFalse(store.get('1')['route_attempted'])
            with patch('technician_sat.TechnicianSatPreparer') as cls:
                cls.return_value.prepare.side_effect=prepare
                cls.return_value.prepare_route.return_value={"ready":True}
                result=run_live([plan.item],'technician_sat_external',technician_plans=[plan],
                    recovery_store=store,session_factory=factory)
            self.assertEqual(result[0].status,'success')
            self.assertEqual(server.routed['1'],1);self.assertEqual(server.sent['1'],1)
            self.assertEqual(server.details_sent['1'],1)
            self.assertEqual(store.get('1')['verified_status'],'ISSUE')


    def test_sat_ok_waits_for_editor_response_and_unobstructed_button(self):
        from warehouse_transport import WarehouseSession
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        session=WarehouseSession.__new__(WarehouseSession)
        session.driver=Mock();session.reader=Mock();session.check=Mock()
        events=[];body=Mock();body.text=''
        def keys(*args):
            if args==(Keys.BACKSPACE,):body.text=''
            elif args==(Keys.TAB,):events.append('tab')
            elif args[0]!=Keys.CONTROL:body.text+=args[0]
        body.send_keys.side_effect=keys
        button=Mock();button.text='OK';button.click.side_effect=lambda:events.append('ok')
        dialog=Mock();dialog.text='SAT Externo\nDetalles:'
        dialog.get_attribute.return_value='ENVIAR_SAT_EXT-dialog_inner'
        dialog.find_elements.side_effect=lambda by,tag:[Mock()] if tag=='iframe' else [button]
        session.reader.dialogs.return_value=[dialog]
        def response():
            events.append('response')
            return events.count('response')-1
        session.reader.response_sequence.side_effect=response
        def wait(predicate,label):
            for attempt in range(3):
                result=predicate(None)
                if result:return result
            raise AssertionError('No condition met: '+label)
        session.reader.wait.side_effect=wait
        session.driver.find_element.return_value=body
        # First hit-test is blocked; no confirmation is marked or sent yet.
        session.driver.execute_script.side_effect=[False,True]
        session.sat_details('technician_sat_external','NO ADMITE','APPR',{},lambda:events.append('mark'))
        self.assertLess(events.index('tab'),len(events)-events[::-1].index('response')-1)
        self.assertLess(events.index('mark'),events.index('ok'))
        self.assertEqual(events.count('ok'),1);self.assertEqual(events.count('mark'),1)
        self.assertEqual(session.driver.execute_script.call_count,2)


    def test_technical_lost_details_response_is_reverified_without_resending(self):
        from pathlib import Path
        from unittest.mock import patch
        from tests.test_support import temporary_directory
        from tests.test_warehouse_recovery import FakeServer
        from warehouse_recovery import RecoveryStore
        from warehouse_transport import run_live
        server=FakeServer(action='technician_sat_external',states={'1':'APPR'})
        server.lost_details.add('1');original=server.session
        def factory():
            session=original()
            session.accept_button.return_value.click.side_effect=lambda:server.sent.update(['1'])
            return session
        plan,=reviewed_sat_plans([WarehouseItem('1')],self.values(),default_selection())
        with temporary_directory() as folder,patch('technician_sat.TechnicianSatPreparer') as cls:
            cls.return_value.prepare_route.return_value={'ready':True}
            store=RecoveryStore(Path(folder))
            result=run_live([plan.item],'technician_sat_external',technician_plans=[plan],
                recovery_store=store,session_factory=factory)
        self.assertEqual(result[0].status,'success')
        self.assertEqual(server.routed['1'],1);self.assertEqual(server.sent['1'],1)
        self.assertEqual(server.details_sent['1'],1)


    def test_route_readiness_waits_for_native_response_before_testing_controls(self):
        from technician_sat import TechnicianSatPreparer
        p=TechnicianSatPreparer(Mock(),'1',timeout=1)
        p.require_approved=Mock();p.tab=Mock();p.idle=Mock()
        events=[]
        responses=iter((10,10,11))
        def response():
            value=next(responses);events.append(('response',value));return value
        p.response_sequence=Mock(side_effect=response)
        def execute(script,*args):
            if not args:return False  # Tab was not active before the click.
            events.append(('controls',None))
            return {'ready':True,'ot':'1','status':'APPR','asset':'A','plant':'LAB-BAD',
                    'active_tab':True,'route_reachable':True}
        p.driver.execute_script.side_effect=execute
        result=p.prepare_route()
        self.assertEqual(result['response_after'],11)
        self.assertLess(events.index(('response',11)),events.index(('controls',None)))
        p.tab.assert_called_once_with('Orden de trabajo')
        p.driver.find_element.assert_not_called()

    def test_route_readiness_does_not_click_when_controls_remain_blocked(self):
        from technician_sat import TechnicianSatPreparer
        p=TechnicianSatPreparer(Mock(),'1',timeout=0.1)
        p.require_approved=Mock();p.tab=Mock();p.idle=Mock()
        p.response_sequence=Mock(return_value=10)
        p.driver.execute_script.side_effect=[True,{'ready':False},{'ready':False}]
        with self.assertRaises(RuntimeError):p.prepare_route()
        p.driver.find_element.assert_not_called()

    def test_native_bmx_error_is_not_replaced_by_generic_selector_message(self):
        from warehouse_transport import WarehouseSession
        from workorder_start import WorkorderStarter
        reader=WorkorderStarter(Mock(),'1')
        reader.dialog_snapshot=Mock(return_value=[{'id':'msgbox-dialog_inner',
            'text':'BMXAA4214E - Se ha producido un error desconocido.'}])
        session=WarehouseSession.__new__(WarehouseSession);session.reader=reader
        with self.assertRaisesRegex(RuntimeError,'BMXAA4214E'):
            session.choice('Enviar a SAT Externo')
        reader.driver.find_element.assert_not_called()

    def test_failed_reverification_keeps_original_native_error(self):
        from pathlib import Path
        from tests.test_support import temporary_directory
        from tests.test_warehouse_recovery import FakeServer
        from warehouse_recovery import RecoveryStore
        from warehouse_transport import reverify_pending
        server=FakeServer(action='technician_sat_external',states={'1':'APPR'})
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder))
            record=store.begin(WarehouseItem('1'),'technician_sat_external',
                {'Activo':'ASSET-1','Nº de serie':'SERIAL-1','Planta':'LAB-BAD'},'APPR',0)
            record=store.update(record,'route_attempted',last_error='Maximo requiere revisión: BMXAA4214E')
            result,=reverify_pending([record],recovery_store=store,session_factory=server.session)
        self.assertIn('BMXAA4214E',result.detail);self.assertIn('APPR',result.detail)
        self.assertFalse(server.routed);self.assertFalse(server.sent)


    def test_technical_preparation_and_routing_use_one_session(self):
        from pathlib import Path
        from unittest.mock import patch
        from tests.test_support import temporary_directory
        from tests.test_warehouse_recovery import FakeServer
        from warehouse_recovery import RecoveryStore
        from warehouse_transport import run_live
        server=FakeServer(action='technician_sat_external',states={'1':'APPR'})
        original=server.session;events=[]
        def factory():
            session=original()
            session.accept_button.return_value.click.side_effect=lambda:server.sent.update(['1'])
            history=session.history_count.side_effect
            def count(caption):events.append('history');return history(caption)
            session.history_count.side_effect=count
            return session
        plan,=reviewed_sat_plans([WarehouseItem('1')],self.values(),default_selection())
        preparing=Mock()
        preparing.prepare.side_effect=lambda _:events.append('prepare')
        preparing.prepare_route.return_value={'ready':True}
        with temporary_directory() as folder,patch('technician_sat.TechnicianSatPreparer',return_value=preparing):
            result=run_live([plan.item],'technician_sat_external',technician_plans=[plan],
                recovery_store=RecoveryStore(Path(folder)),session_factory=factory)
        self.assertEqual(result[0].status,'success')
        self.assertEqual(len(server.sessions),1)
        preparing.prepare.assert_called_once_with(plan)
        self.assertLess(events.index('prepare'),events.index('history'))
        self.assertEqual(server.routed['1'],1);self.assertEqual(server.sent['1'],1)

    def test_changed_identity_after_preparation_stops_before_routing(self):
        from pathlib import Path
        from unittest.mock import patch
        from tests.test_support import temporary_directory
        from tests.test_warehouse_recovery import FakeServer
        from warehouse_recovery import RecoveryStore
        from warehouse_transport import run_live
        server=FakeServer(action='technician_sat_external',states={'1':'APPR'})
        original=server.session
        def factory():
            session=original()
            def check(state,identity):
                if '1' in server.identity_changed:raise RuntimeError('Identity changed')
            session.check.side_effect=check
            return session
        plan,=reviewed_sat_plans([WarehouseItem('1')],self.values(),default_selection())
        with temporary_directory() as folder,patch('technician_sat.TechnicianSatPreparer') as cls:
            cls.return_value.prepare.side_effect=lambda _:server.identity_changed.add('1')
            store=RecoveryStore(Path(folder))
            result=run_live([plan.item],'technician_sat_external',technician_plans=[plan],
                recovery_store=store,session_factory=factory,auto_recheck=False)
            self.assertEqual(store.get('1')['phase'],'preparing')
            self.assertFalse(store.get('1')['route_attempted'])
        self.assertEqual(result[0].status,'failed')
        self.assertEqual(result[0].step,'Preparación incompleta')
        self.assertFalse(server.routed);self.assertFalse(server.sent)

    def test_native_reload_reuses_driver_and_checks_state(self):
        from unittest.mock import patch
        from technician_sat import TechnicianSatPreparer
        p=TechnicianSatPreparer(Mock(),'1');p.require_approved=Mock();p.idle=Mock()
        with patch('maximo_client.open_workorders_app') as opened, patch('maximo_client.read_workorder_status',return_value='APPR') as read:
            p.reload_workorder()
        opened.assert_called_once_with(p.driver,headless=True)
        read.assert_called_once_with(p.driver,'1')
        p.driver.refresh.assert_not_called()
        with patch('maximo_client.open_workorders_app'), patch('maximo_client.read_workorder_status',return_value='ISSUE'):
            with self.assertRaisesRegex(RuntimeError,'cambió de estado'):p.reload_workorder()

    def test_changed_anomaly_class_in_new_context_is_rejected(self):
        preparer=self.preparer();preparer.incident_present=Mock(return_value=True)
        preparer.value=Mock(side_effect=lambda caption:'0,75' if caption=='Horas totales de reparación' else 'OTHER')
        preparer.verify_failure_rows=Mock();preparer.route=Mock()
        plan,=reviewed_sat_plans([WarehouseItem('1')],self.values(),default_selection())
        with self.assertRaisesRegex(RuntimeError,'clase de anomalía'):
            preparer.verify_prepared(plan)
        preparer.route.assert_not_called()
