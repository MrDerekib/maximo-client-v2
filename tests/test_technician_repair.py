import tests
from datetime import datetime,timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QMessageBox
from warehouse import WarehouseItem
from warehouse_recovery import RecoveryStore
from failure_catalog import default_selection
from technician_repair import reviewed_repair,run_repair,RepairPreparer
from technician_repair_ui import RepairDialog
from tests.test_support import temporary_directory


class RepairPlanTests(TestCase):
    def values(self):
        return {'reference':'stock Ávila: libre','duration':'1','time':'2026-11-11T10:00:00',
            'time_mode':'end','action':'discard','justification':'Prueba sin reparación posible',
            'entries':[{'summary':'Test equipo','details':'Aviso sobretensión'},
                       {'summary':'Comprobación','details':'Resultado de prueba'}]}
    def plan(self):return reviewed_repair(WarehouseItem('1',serial='S'),self.values(),default_selection())
    def test_free_reference_entries_and_calculated_start(self):
        p=self.plan()
        self.assertEqual(p.reference,'stock Ávila: libre');self.assertEqual(len(p.entries),2)
        self.assertEqual(p.start,'2026-11-11T09:00:00');self.assertEqual(p.end,'2026-11-11T10:00:00')
    def test_incident_prefix_is_added_once_for_numbers_and_free_text(self):
        for value,expected in (('36316003','inc: 36316003'),('stock Ávila','inc: stock Ávila'),
                ('inc: 36316003','inc: 36316003'),(' INC: stock TMB ','inc: stock TMB')):
            with self.subTest(value=value):
                plan=reviewed_repair(WarehouseItem('1'),{**self.values(),'reference':value},default_selection())
                self.assertEqual(plan.incident_summary,expected)
        with self.assertRaises(ValueError):
            reviewed_repair(WarehouseItem('1'),{**self.values(),'reference':'inc: '},default_selection())

    def test_start_mode_calculates_end_and_quarters_are_required(self):
        values=self.values();values.update(time_mode='start',duration='0,25')
        p=reviewed_repair(WarehouseItem('1'),values,default_selection())
        self.assertEqual(p.end,'2026-11-11T10:15:00')
        values['duration']='0,1'
        with self.assertRaises(ValueError):reviewed_repair(WarehouseItem('1'),values,default_selection())
    def test_future_end_or_missing_discard_reason_is_rejected(self):
        for update in ({'time':'2099-01-01T00:00:00'},{'justification':''},{'reference':''},{'action':'retain'}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                reviewed_repair(WarehouseItem('1'),{**self.values(),**update},default_selection())
    def test_duplicate_summaries_or_details_without_summary_are_rejected(self):
        for entries in ([{'summary':'Test'},{'summary':'Test'}],[{'details':'Result'}]):
            with self.subTest(entries=entries),self.assertRaises(ValueError):
                reviewed_repair(WarehouseItem('1'),{**self.values(),'entries':entries},default_selection())
    def test_normal_close_reuses_plan_without_discard_reason(self):
        p=reviewed_repair(WarehouseItem('1'),{**self.values(),'action':'close','justification':''},default_selection())
        self.assertEqual(p.action,'close')

    def test_pending_record_blocks_before_browser_is_opened(self):
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder));p=self.plan()
            store.begin(p.item,'technician_discard',{'Activo':'A','Nº de serie':'S','Planta':'LAB-BAD'},'INPRG',preparing=True)
            factory=Mock()
            with self.assertRaisesRegex(RuntimeError,'pendiente'):run_repair(p,store=store,session_factory=factory)
            factory.assert_not_called()

    def test_incompatible_live_state_stops_before_writes(self):
        s=Mock();s.open.return_value='ISSUE'
        with temporary_directory() as folder,self.assertRaises(RuntimeError):run_repair(self.plan(),store=RecoveryStore(Path(folder)),session_factory=lambda:s)
        s.driver.find_element.assert_not_called();s.close.assert_called_once()

    def test_preparation_failure_records_request_without_routing(self):
        s=Mock();s.open.return_value='APPR';s.identity.return_value={'Activo':'A','Nº de serie':'S','Planta':'LAB-BAD'}
        with temporary_directory() as folder,patch('technician_repair.RepairPreparer') as cls:
            store=RecoveryStore(Path(folder));cls.return_value.apply_anomalies.side_effect=RuntimeError('Save rejected')
            with self.assertRaisesRegex(RuntimeError,'Save rejected'):run_repair(self.plan(),store=store,session_factory=lambda:s)
            record=store.get('1');self.assertFalse(record['route_attempted'])
            self.assertEqual(record['reviewed_request']['reference'],'stock Ávila: libre')
            self.assertIn('Save rejected',record['last_error'])
        s.driver.find_element.assert_not_called()

    def test_discard_reload_accepts_close_but_normal_close_does_not(self):
        from technician_repair import RepairCloser
        from dataclasses import replace
        session=Mock();plan=self.plan()
        closer=RepairCloser(session,plan,Mock(),Mock(),{})
        closer.idle=Mock();closer.check_ot=Mock();closer.reject_dialogs=Mock()
        with patch('maximo_client.open_workorders_app'),patch('maximo_client.read_workorder_status',return_value='CLOSE'):
            closer.reload_workorder()
            closer.plan=replace(plan,action='close')
            with self.assertRaisesRegex(RuntimeError,'CLOSE'):closer.reload_workorder()

    def test_discard_recovery_reads_history_and_dates_without_resending(self):
        from warehouse_transport import reverify_pending
        with temporary_directory() as folder:
            store=RecoveryStore(Path(folder));plan=self.plan()
            identity={'Activo':'A','Nº de serie':'S','Planta':'LAB-BAD'}
            record=store.begin(plan.item,'technician_discard',identity,'APPR',history_before=0,preparing=True,reviewed_request={'item':{'ot':'1'}})
            record=store.update(record,'details_attempted',confirmation_attempted=True,details_attempted=True)
            session=Mock();session.open.return_value='CLOSE';session.identity.return_value=identity
            session.verify.return_value='CLOSE';session.history_count.return_value=1
            with patch('technician_repair.verify_saved_repair') as dates:
                result,=reverify_pending([record],recovery_store=store,session_factory=lambda:session)
            self.assertEqual(result.status,'success');self.assertEqual(result.verified_status,'CLOSE')
            dates.assert_called_once();session.driver.find_element.assert_not_called();session.accept_button.assert_not_called()

    def test_existing_entry_with_other_details_is_never_overwritten(self):
        from technician_repair import RepairEntry
        p=RepairPreparer(Mock(),'1','APPR');p.open_entry=Mock(return_value=True);p.details=Mock(return_value='Original')
        p.ensure_incident=Mock()
        with self.assertRaisesRegex(RuntimeError,'otros detalles'):p.ensure_entry(RepairEntry('Test','Different'))
        p.ensure_incident.assert_not_called();p.details.assert_called_once_with()

    def test_appr_and_inprg_share_completion_and_appr_only_starts_once(self):
        for state in ('APPR','INPRG'):
            with self.subTest(state=state),temporary_directory() as folder,patch('technician_repair.RepairPreparer') as pre,patch('technician_repair.RepairCloser') as closer,patch('technician_repair.verify_repair_entries') as verified_entries:
                s=Mock();s.open.return_value=state;s.identity.return_value={'Activo':'A','Nº de serie':'S','Planta':'LAB-BAD'}
                s.history_count.side_effect=[0,1]
                def complete(approval,pending):
                    mark=closer.call_args.args[2]
                    mark('route_attempted',route_attempted=True)
                    mark('confirmation_attempted',confirmation_attempted=True)
                    mark('details_attempted',details_attempted=True)
                    return {'ot':'1','status':'CLOSE','action':'discard'}
                closer.return_value.run_close.side_effect=complete
                store=RecoveryStore(Path(folder))
                result=run_repair(self.plan(),store=store,session_factory=lambda:s)
                self.assertEqual(result['status'],'CLOSE')
                verified_entries.assert_called_once()
                self.assertTrue(closer.return_value.run_close.call_args.args[1]['prepared_in_place'])
                self.assertEqual(store.get('1')['phase'],'verified')
                self.assertEqual(store.get('1')['history_after'],1)
                self.assertEqual(pre.return_value.run.call_count,1 if state=='APPR' else 0)
                self.assertEqual(pre.return_value.ensure_entry.call_count,3)
                self.assertEqual(pre.return_value.ensure_entry.call_args_list[0].args[0].summary,'inc: stock Ávila: libre')
                closer.return_value.run_close.assert_called_once()
                s.close.assert_called_once()

    def test_closed_workflow_never_prints_or_repeats_after_uncertain_confirmation(self):
        s=Mock();s.open.return_value='INPRG';s.identity.return_value={'Activo':'A','Nº de serie':'S','Planta':'LAB-BAD'}
        s.history_count.return_value=0
        with temporary_directory() as folder,patch('technician_repair.RepairPreparer'),patch('technician_repair.RepairCloser') as cls:
            store=RecoveryStore(Path(folder))
            def fail(approval,pending):
                mark=cls.call_args.args[2];mark('confirmation_attempted',confirmation_attempted=True)
                raise TimeoutError('Response lost')
            cls.return_value.run_close.side_effect=fail
            with self.assertRaises(TimeoutError):run_repair(self.plan(),store=store,session_factory=lambda:s)
            self.assertTrue(store.get('1')['confirmation_attempted'])
            self.assertEqual(cls.return_value.run_close.call_count,1)


class RepairUiTests(TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def dialog(self):
        d=RepairDialog(WarehouseItem('1',serial='S'),default_selection(),autoload=False)
        self.addCleanup(d.deleteLater)
        d.preview_ready({'state':'APPR','fault':'Cached fault','duration':'1','reference':'inc: 123',
            'entries':[{'summary':'Test','details':'Result'}]})
        d.justification.setPlainText('Irreparable');return d
    def test_discard_reason_defaults_to_local_fault_without_waiting_for_preview(self):
        with patch('technician_repair_ui.get_fault_description',return_value='PETARDEA NO FUNCIONA'):
            d=RepairDialog(WarehouseItem('1'),default_selection(),autoload=False)
        self.addCleanup(d.deleteLater)
        self.assertEqual(d.justification.toPlainText(),'PETARDEA NO FUNCIONA')
        self.assertEqual(d.values()['justification'],'PETARDEA NO FUNCIONA')
        self.assertFalse(d._justification_edited)

    def test_preview_fault_fills_reason_but_never_overwrites_manual_edits_or_clear(self):
        preview={'state':'INPRG','fault':'Avería desde Maximo','duration':'0,5','reference':'inc: stock','entries':[]}
        for edit in (None,'Motivo escrito por el usuario',''):
            with self.subTest(edit=edit),patch('technician_repair_ui.get_fault_description',return_value='Avería local'):
                d=RepairDialog(WarehouseItem('1'),default_selection(),autoload=False)
                self.addCleanup(d.deleteLater)
                if edit is not None:d.justification.setPlainText(edit)
                d.preview_ready(preview)
                self.assertEqual(d.justification.toPlainText(),preview['fault'] if edit is None else edit)
                self.assertFalse(d.confirm.isChecked())

    def test_live_fault_initializes_missing_local_reason_and_remains_discard_only(self):
        with patch('technician_repair_ui.get_fault_description',return_value=''):
            d=RepairDialog(WarehouseItem('1'),default_selection(),autoload=False,default_action='close')
        self.addCleanup(d.deleteLater)
        d.preview_ready({'state':'INPRG','fault':'Fallo de alimentación','duration':'1','reference':'inc: stock','entries':[]})
        self.assertEqual(d.values()['justification'],'')
        d.action.setCurrentIndex(d.action.findData('discard'))
        self.assertEqual(d.values()['justification'],'Fallo de alimentación')
        self.assertTrue(d.review_form.isRowVisible(d.justification))

    def test_slow_preview_does_not_erase_incident_duration_or_new_worklogs(self):
        with patch('technician_repair_ui.get_fault_description',return_value='Avería local'):
            d=RepairDialog(WarehouseItem('1'),default_selection(),autoload=False)
        self.addCleanup(d.deleteLater)
        d.reference.setText('36281696');d.duration.setText('0,5')
        d.add_entry('Test equipo','Resultado escrito mientras carga')
        d.time_mode.setCurrentIndex(d.time_mode.findData('start'))
        chosen=d.time.dateTime().addSecs(-3600);d.time.setDateTime(chosen)
        d.preview_ready({'state':'INPRG','fault':'Avería local','duration':'','reference':'',
            'entries':[{'summary':'Registro anterior','details':'Desde Maximo'}]})
        self.assertEqual(d.reference.text(),'36281696')
        self.assertEqual(d.duration.text(),'0,5')
        self.assertEqual(d.values()['entries'],[{'summary':'Test equipo','details':'Resultado escrito mientras carga'}])
        self.assertEqual(d.time_mode.currentData(),'start');self.assertEqual(d.time.dateTime(),chosen)
        self.assertIn('conservado',d.status.text())

    def test_user_cleared_fields_and_removed_rows_stay_empty_after_new_preview(self):
        d=self.dialog()
        d.reference.clear();d.duration.clear();d.entries.removeRow(0)
        d.preview_ready({'state':'INPRG','fault':'Avería','duration':'2','reference':'inc: anterior',
            'entries':[{'summary':'Test','details':'Result'}]})
        self.assertEqual(d.reference.text(),'');self.assertEqual(d.duration.text(),'')
        self.assertEqual(d.entries.rowCount(),0)

    def test_untouched_fields_load_and_repeated_preview_does_not_duplicate_rows(self):
        with patch('technician_repair_ui.get_fault_description',return_value=''):
            d=RepairDialog(WarehouseItem('1'),default_selection(),autoload=False)
        self.addCleanup(d.deleteLater)
        data={'state':'INPRG','fault':'Avería','duration':'1','reference':'inc: anterior',
            'entries':[{'summary':'Test','details':'Result'}]}
        d.preview_ready(data);d.preview_ready(data)
        self.assertEqual(d.reference.text(),'inc: anterior');self.assertEqual(d.duration.text(),'1')
        self.assertEqual(d.entries.rowCount(),1);self.assertFalse(d._preview_edited)
        d.entries.cellWidget(0,1).setPlainText('Resultado modificado')
        d.preview_ready(data)
        self.assertEqual(d.values()['entries'][0]['details'],'Resultado modificado')

    def test_context_entry_sets_the_requested_action_without_launching(self):
        for action in ('discard','close'):
            with self.subTest(action=action):
                d=RepairDialog(WarehouseItem('1'),default_selection(),autoload=False,default_action=action)
                self.addCleanup(d.deleteLater)
                self.assertEqual(d.action.currentData(),action)
                self.assertEqual(d.review_form.isRowVisible(d.justification),action=='discard')
                self.assertEqual(d.print_check.text(),'Imprimir parte una vez verificado')
                self.assertFalse(d.confirm.isChecked());self.assertIsNone(d._worker)
        with self.assertRaises(ValueError):
            RepairDialog(WarehouseItem('1'),default_selection(),autoload=False,default_action='other')

    def test_context_menu_has_independent_entries_with_distinct_actions(self):
        from PySide6.QtWidgets import QMenu
        from tests.test_warehouse_ui import Host
        host=Host();self.addCleanup(host.deleteLater);host.table.selectRow(0)
        host.open_repair_completion=Mock()
        menu=QMenu();host.add_repair_completion_action(menu)
        actions=menu.actions()
        self.assertEqual([a.text() for a in actions],['Declarar irreparable · Técnico…','Dar salida · Técnico…'])
        actions[0].trigger();self.assertEqual(host.open_repair_completion.call_args.args[1],'discard')
        actions[1].trigger();self.assertEqual(host.open_repair_completion.call_args.args[1],'close')

    def test_opening_review_does_not_launch_or_print(self):
        d=self.dialog();self.assertIsNone(d._worker);self.assertFalse(d.retry_print.isEnabled())
        self.assertEqual(d.entries.rowCount(),1)
    def test_details_can_contain_multiple_lines_without_creating_extra_entries(self):
        d=self.dialog();d.entries.cellWidget(0,1).setPlainText('Prueba 1\nPrueba 2')
        self.assertEqual(d.values()['entries'][0]['details'],'Prueba 1\nPrueba 2')
        self.assertEqual(d.entries.rowCount(),1)

    def test_checkbox_and_modal_confirmation_are_both_required(self):
        d=self.dialog()
        with patch.object(d,'launch') as launch,patch('technician_repair_ui.QMessageBox.warning'),patch('technician_repair_ui.QMessageBox.question') as question:d.execute()
        launch.assert_not_called();question.assert_not_called()
        d.confirm.setChecked(True)
        with patch.object(d,'launch') as launch,patch('technician_repair_ui.QMessageBox.question',return_value=QMessageBox.No):d.execute()
        launch.assert_not_called()
        with patch.object(d,'launch') as launch,patch('technician_repair_ui.QMessageBox.question',return_value=QMessageBox.Yes):d.execute()
        launch.assert_called_once();self.assertEqual(launch.call_args.args[0].reference,'inc: 123')
    def test_action_change_resets_irreversible_confirmation(self):
        d=self.dialog();d.confirm.setChecked(True);d.action.setCurrentIndex(1)
        self.assertFalse(d.confirm.isChecked())
        self.assertFalse(d.review_form.isRowVisible(d.justification))
        self.assertEqual(d.values()['justification'],'')
        d.action.setCurrentIndex(0)
        self.assertTrue(d.review_form.isRowVisible(d.justification))
        self.assertEqual(d.justification.toPlainText(),'Irreparable')
    def test_execution_opens_separate_progress_and_hides_review(self):
        d=self.dialog();d.show()
        from technician_repair import reviewed_repair
        plan=reviewed_repair(d.item,d.values(),default_selection())
        with patch('technician_repair_ui.RepairWorker') as worker:
            worker.return_value.isRunning.return_value=False
            d.launch(plan)
            self.assertFalse(d.isVisible());self.assertTrue(d.progress_dialog.isVisible())
            worker.return_value.stage.connect.assert_called_once()
            worker.return_value.start.assert_called_once()
            d.progress_dialog.close();d.progress_dialog.deleteLater()

    def test_progress_checks_only_completed_phases(self):
        from technician_repair_ui import RepairProgressDialog
        d=self.dialog();progress=RepairProgressDialog(d);self.addCleanup(progress.deleteLater)
        progress.set_stage(3,'Duración y fechas')
        self.assertEqual(progress.table.item(2,1).text(),'Completado')
        self.assertEqual(progress.table.item(3,1).text(),'En curso')
        self.assertEqual(progress.table.item(4,1).text(),'Pendiente')
        progress.failure('Verification needed')
        self.assertEqual(progress.table.item(3,1).text(),'Revisar resultado')
        self.assertFalse(progress.print_button.isEnabled())

    def test_discard_success_saves_close_locally_and_enables_only_print_retry(self):
        d=self.dialog()
        with patch('technician_repair_ui.apply_warehouse_status',return_value=True) as save,patch('technician_repair_ui.apply_closed_repair') as old,patch('technician_repair_ui.RecoveryStore'):
            d.finished_repair({'ot':'1','status':'CLOSE','operation_id':'operation','print_report':False})
        save.assert_called_once_with('1','CLOSE');old.assert_not_called()
        self.assertTrue(d.retry_print.isEnabled())

    def test_application_stop_requests_preserve_active_worker(self):
        from threading import Event
        d=self.dialog();worker=Mock();worker.stop_requested=Event();d._worker=worker
        d.request_stop()
        self.assertTrue(worker.stop_requested.is_set())
        worker.terminate.assert_not_called()
        worker.isRunning.return_value=False

    def test_date_dropdown_opens_calendar_with_hour_and_minutes(self):
        from PySide6.QtCore import Qt,QPoint,QDate,QTime,QDateTime
        from PySide6.QtTest import QTest
        d=self.dialog();d.time.setDateTime(QDateTime(QDate(2026,11,11),QTime(14,17)))
        d.show();self.app.processEvents()
        QTest.mouseClick(d.time,Qt.LeftButton,pos=QPoint(d.time.width()-15,d.time.height()//2))
        popup=d.time._date_time_popup;self.addCleanup(popup.reject)
        self.assertTrue(popup.isVisible())
        self.assertEqual(popup.hour.currentData(),14);self.assertEqual(popup.minute.currentData(),17)
        choices=[popup.minute.itemData(i) for i in range(popup.minute.count())]
        self.assertTrue(all(value%5==0 for value in choices if value!=17))
        self.assertFalse(d.time.calendarWidget().isVisible())
        popup.calendar.setSelectedDate(QDate(2026,11,10))
        popup.hour.setCurrentIndex(popup.hour.findData(15));popup.minute.setCurrentIndex(popup.minute.findData(20))
        popup.apply_button.click()
        self.assertEqual(d.time.dateTime().toString('yyyy-MM-dd HH:mm'),'2026-11-10 15:20')
        self.assertIn('14:20',d.dates.text())

    def test_cancel_date_and_time_selection_keeps_the_previous_value(self):
        from PySide6.QtCore import QDate
        d=self.dialog();before=d.time.dateTime()
        d.time.show_date_time_popup();popup=d.time._date_time_popup
        self.addCleanup(popup.reject)
        popup.calendar.setSelectedDate(QDate(2026,11,9));popup.hour.setCurrentIndex(0)
        popup.reject()
        self.assertEqual(d.time.dateTime(),before)

    def test_failure_keeps_print_disabled(self):
        d=self.dialog();signals=[];d.print_requested.connect(signals.append);d.failed('Not verified')
        self.assertFalse(d.retry_print.isEnabled());self.assertFalse(signals)
    def test_verified_result_print_retry_never_launches_repair_again(self):
        d=self.dialog();signals=[];d.print_requested.connect(signals.append)
        with patch('technician_repair_ui.apply_closed_repair',return_value=True),patch('technician_repair_ui.RecoveryStore'):
            d.finished_repair({'ot':'1','status':'ISSUE','operation_id':'operation','print_report':True})
        self.assertEqual(signals,['1']);self.assertTrue(d.retry_print.isEnabled())
        with patch.object(d,'launch') as launch:d.retry_print.click();d.execute()
        launch.assert_not_called();self.assertEqual(signals,['1','1'])


class CachedFaultTests(TestCase):
    def test_sat_defaults_use_cached_fault_without_reading_live_summary(self):
        from technician_sat import technician_sat_defaults
        s=Mock();s.open.return_value='APPR';s.identity.return_value={'Activo':'A','Planta':'P','Nº de serie':'S'}
        s.reader.value.return_value='0,50'
        with patch('technician_sat.get_fault_description',return_value='Cached fault'):
            result=technician_sat_defaults([WarehouseItem('1',serial='S')],session_factory=lambda:s)
        self.assertEqual(result['1']['reason'],'Cached fault')
        self.assertNotIn(('Resumen',),[call.args for call in s.reader.value.call_args_list])
    def test_empty_cached_fault_falls_back_to_live_summary(self):
        from technician_sat import technician_sat_defaults
        s=Mock();s.open.return_value='APPR';s.identity.return_value={'Activo':'A','Planta':'P','Nº de serie':'S'}
        s.reader.value.side_effect=['Live fault','0,50']
        with patch('technician_sat.get_fault_description',return_value=''):
            result=technician_sat_defaults([WarehouseItem('1',serial='S')],session_factory=lambda:s)
        self.assertEqual(result['1']['reason'],'Live fault')
