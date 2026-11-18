"""Manual cache refresh and one-time automatic reads, without Maximo access."""
import tests
import sqlite3
from contextlib import ExitStack, closing
from datetime import datetime
from unittest import TestCase
from unittest.mock import Mock, patch
from tests import test_filters as fixtures
import db
import updater


class InformationRefreshTests(TestCase):
    def setUp(self):
        self.f=fixtures.FilterTests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
        with closing(sqlite3.connect(self.f.path)) as conn:
            conn.execute('UPDATE maximo SET Activo=1');conn.commit()

    def test_successful_empty_reads_are_not_polled_again(self):
        self.assertTrue(db.apply_fault_description('1',''))
        self.assertTrue(db.apply_detailed_description('1','',''))
        self.assertNotIn('1',db.fault_description_candidates(minimum_age_hours=None))
        self.assertNotIn('1',db.detailed_description_candidates(minimum_age_hours=None))

    def test_all_recent_failures_wait_24_hours_but_manual_pending_scan_can_ignore_wait(self):
        for ot in ('1','2','3','4'):
            db.mark_fault_description_attempt(ot);db.mark_detailed_description_attempt(ot)
        self.assertEqual(db.fault_description_candidates(),[])
        self.assertEqual(db.detailed_description_candidates(),[])
        self.assertEqual(set(db.detailed_description_candidates(minimum_age_hours=None)),{'1','2','3','4'})

    def test_forced_refresh_overwrites_only_requested_fields_even_when_inactive(self):
        db.apply_fault_description('1','Old fault');db.apply_detailed_description('1','Old detail','Old detail')
        with closing(sqlite3.connect(self.f.path)) as conn:
            conn.execute("UPDATE maximo SET Activo=0,Seguimiento='CLOSE' WHERE OT='1'");conn.commit()
        self.assertFalse(db.apply_fault_description('1','No automatic overwrite'))
        self.assertTrue(db.apply_fault_description('1','Updated',force=True))
        self.assertTrue(db.apply_detailed_description('1','','',force=True))
        with closing(sqlite3.connect(self.f.path)) as conn:
            row=conn.execute("SELECT Descripcion_averia,Descripcion_detallada_texto,Activo,Seguimiento FROM maximo WHERE OT='1'").fetchone()
        self.assertEqual(row,('Updated','',0,'CLOSE'))

    def worker(self,fault,detail,status=None):
        stack=ExitStack();self.addCleanup(stack.close)
        for name,value in [('create_edge_profile','fake-profile'),('setup_driver',Mock()),('login',None),('open_workorders_app',None),('cleanup_edge_profile',None)]:
            stack.enter_context(patch.object(updater,name,return_value=value))
        stack.enter_context(patch.object(updater,'read_workorder_status',side_effect=status,return_value='CLOSE'))
        stack.enter_context(patch.object(updater,'read_workorder_fault_description',side_effect=fault))
        stack.enter_context(patch.object(updater,'read_workorder_detailed_description',side_effect=detail))
        return stack

    def test_manual_worker_refreshes_both_fields_and_only_explicit_selection(self):
        self.worker(['New fault'],[('New detail','<p>New detail</p>')])
        progress=Mock()
        with patch.object(updater,'fault_description_candidates') as candidates,patch.object(updater,'detailed_description_candidates') as details:
            self.assertEqual(updater.enrich_fault_descriptions(limit=None,force_ots=['1','1'],include_fault=False,include_detail=False,progress_callback=progress),3)
        candidates.assert_not_called();details.assert_not_called()
        self.assertEqual(db.get_detailed_description('1')[0],'New detail')
        progress.assert_called_once_with(1,1,'1')
        with closing(sqlite3.connect(self.f.path)) as conn:
            self.assertIsNone(conn.execute("SELECT Ultima_lectura_averia FROM maximo WHERE OT='2'").fetchone()[0])

    def test_failed_forced_reads_preserve_old_cache_and_success_timestamps(self):
        stamp='2026-01-01T08:00:00'
        db.apply_fault_description('1','Old fault',stamp);db.apply_detailed_description('1','Old detail','Old detail',stamp)
        self.worker([RuntimeError('Cannot read fault')],[RuntimeError('Cannot read detail')])
        with self.assertLogs(level='WARNING'):
            self.assertEqual(updater.enrich_fault_descriptions(limit=None,force_ots=['1']),1)
        with closing(sqlite3.connect(self.f.path)) as conn:
            row=conn.execute("SELECT Descripcion_averia,Descripcion_detallada_texto,Ultima_lectura_averia,Ultima_lectura_detallada FROM maximo WHERE OT='1'").fetchone()
        self.assertEqual(row,('Old fault','Old detail',stamp,stamp))

    def test_ui_sends_only_selection_as_manual_job_and_releases_counters(self):
        with self.f.qt_window() as (w,qt):
            with patch.object(w,'_credentials_ready',return_value=True),patch.object(w,'_start_task') as start:
                w.refresh_selected_information(('1','2','1'))
                function,done,failed=start.call_args.args
                with patch.object(qt,'enrich_fault_descriptions',return_value=4) as read:
                    function(Mock())
                self.assertEqual(read.call_args.kwargs['force_ots'],('1','2'))
                self.assertEqual(read.call_args.kwargs['job_priority'],qt.MANUAL)
                self.assertTrue(start.call_args.kwargs['coordinated'])
                done(4)
                self.assertFalse(w.update_lock.locked());self.assertFalse(w.fault_description_lock.locked())
                self.assertFalse(w._manual_information_pending)

    def test_ui_start_failure_releases_pending_operation(self):
        with self.f.qt_window() as (w,qt):
            with patch.object(w,'_credentials_ready',return_value=True),patch.object(w,'_start_task',side_effect=RuntimeError('start failed')):
                w.refresh_selected_information(('1',))
            self.assertFalse(w._manual_information_pending)
            self.assertFalse(w.fault_description_lock.locked());self.assertFalse(w.update_lock.locked())

    def test_context_action_is_available_without_enabling_automatic_enrichment(self):
        from PySide6.QtCore import QPoint
        with self.f.qt_window() as (w,qt):
            w.show();qt.QApplication.processEvents()
            index=w.table.model().index(0,1)
            position=w.table.visualRect(index).center()
            menu=qt.QMenu(w)
            try:
                with patch.object(qt,'QMenu',return_value=menu),patch.object(menu,'exec'),patch.object(w,'refresh_selected_information') as refresh:
                    w.show_context_menu(position)
                    action=next(a for a in menu.actions() if a.text().startswith('Actualizar datos desde Maximo'))
                    self.assertTrue(action.isEnabled());action.trigger()
                self.assertEqual(refresh.call_args.args[0],(w.table.item(0,1).text(),))
            finally:menu.deleteLater()

    def test_context_action_freezes_marked_batch(self):
        with self.f.qt_window() as (w,qt):
            w.show();qt.QApplication.processEvents()
            for row in (0,1):w._workorder_selector._toggle_row(w.table.model().index(row,1),qt.Qt.NoModifier)
            expected=tuple(w.table.item(row,1).text() for row in (0,1))
            position=w.table.visualRect(w.table.model().index(0,1)).center()
            menu=qt.QMenu(w)
            try:
                with patch.object(qt,'QMenu',return_value=menu),patch.object(menu,'exec'),patch.object(w,'refresh_selected_information') as refresh:
                    w.show_context_menu(position)
                    action=next(a for a in menu.actions() if a.text().startswith('Actualizar datos desde Maximo'))
                    self.assertIn('(2 OT)',action.text());action.trigger()
                self.assertEqual(refresh.call_args.args[0],expected)
            finally:menu.deleteLater()

    def test_context_refresh_updates_followup_even_if_both_descriptions_fail(self):
        with closing(sqlite3.connect(self.f.path)) as conn:
            conn.execute("UPDATE maximo SET Activo=0,Seguimiento='DAR SALIDA' WHERE OT='1'");conn.commit()
        self.worker([RuntimeError('fault missing')],[RuntimeError('detail missing')])
        with self.assertLogs(level='WARNING'):
            self.assertEqual(updater.enrich_fault_descriptions(limit=None,force_ots=['1']),1)
        with closing(sqlite3.connect(self.f.path)) as conn:
            row=conn.execute("SELECT Seguimiento,Activo,Ultima_comprobacion_estado FROM maximo WHERE OT='1'").fetchone()
        self.assertEqual(row[:2],('CLOSE',0));self.assertIsNotNone(row[2])

    def test_status_failure_does_not_block_description_updates_or_erase_followup(self):
        self.worker(['New fault'],[('New detail','New detail')],status=RuntimeError('status failed'))
        with self.assertLogs(level='WARNING'):
            self.assertEqual(updater.enrich_fault_descriptions(limit=None,force_ots=['1']),2)
        with closing(sqlite3.connect(self.f.path)) as conn:
            row=conn.execute("SELECT Seguimiento,Descripcion_averia,Descripcion_detallada_texto FROM maximo WHERE OT='1'").fetchone()
        self.assertEqual(row,('EN TALLER','New fault','New detail'))

    def test_explicit_status_refresh_handles_active_rows_but_never_erases_on_empty(self):
        self.assertTrue(db.apply_observed_status('1','CLOSE'))
        self.assertFalse(db.apply_observed_status('1','  '))
        with closing(sqlite3.connect(self.f.path)) as conn:
            self.assertEqual(conn.execute("SELECT Seguimiento,Activo FROM maximo WHERE OT='1'").fetchone(),('CLOSE',1))

    def test_existing_loaded_ot_is_reused_for_status_without_a_second_search(self):
        import maximo_client as client
        driver=Mock();number=Mock();state=Mock()
        number.get_attribute.return_value='4448382';state.get_attribute.return_value='CLOSE'
        state.is_displayed.return_value=True
        def find(_by,ident):
            if ident=='mx45-tb':return number
            if ident=='mx73-tb':return state
            raise AssertionError('A second navigation must not occur: '+ident)
        driver.find_element.side_effect=find
        with patch.object(client,'wait_for',side_effect=lambda d,condition,*args,**kwargs:condition(d)):
            self.assertEqual(client.read_workorder_status(driver,'4448382',already_loaded=True),'CLOSE')
        number.clear.assert_not_called()

    def test_status_is_not_read_from_a_different_loaded_ot(self):
        import maximo_client as client
        from selenium.common.exceptions import TimeoutException
        driver=Mock();driver.find_element.return_value.get_attribute.return_value='other OT'
        def wait(d,condition,*args,**kwargs):
            self.assertFalse(condition(d));raise TimeoutException('wrong OT')
        with patch.object(client,'wait_for',side_effect=wait),self.assertRaises(TimeoutException):
            client.read_workorder_status(driver,'4448382',already_loaded=True)
        self.assertEqual([c.args[1] for c in driver.find_element.call_args_list],['mx45-tb'])

    def test_partial_batch_error_refreshes_already_saved_followups(self):
        with self.f.qt_window() as (w,qt):
            with patch.object(w,'_credentials_ready',return_value=True),patch.object(w,'_start_task') as start,patch.object(w,'refresh_table') as refresh:
                w.refresh_selected_information(('1','2'))
                failed=start.call_args.args[2]
                failed('remaining detail reads failed')
                refresh.assert_called_once()
                self.assertFalse(w.update_lock.locked())
