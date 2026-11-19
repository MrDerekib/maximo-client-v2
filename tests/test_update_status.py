import tests
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from update_status import UpdateStatusBar
from tests.test_support import temporary_directory
import updater


class UpdateStatusTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.bar = UpdateStatusBar()
        self.addCleanup(self.bar.deleteLater)
        self.addCleanup(self.bar.finish_progress)

    def test_phase_and_elapsed_persist_beyond_notification_timeout(self):
        with patch('update_status.time.monotonic', return_value=10):
            self.bar.begin_progress()
        with patch('update_status.time.monotonic', return_value=81):
            self.bar.update_progress('Esperando descarga')
        self.assertIn('Esperando descarga', self.bar.currentMessage())
        self.assertIn('01:11', self.bar.currentMessage())
        self.assertTrue(self.bar._timer.isActive())

    def test_foreground_notice_wins_and_latest_phase_returns_when_it_expires(self):
        self.bar.begin_progress()
        self.bar.showMessage('Aviso prioritario', 20)
        self.bar.update_progress('Guardando cambios')
        self.assertEqual(self.bar.currentMessage(), 'Aviso prioritario')
        QTest.qWait(80)
        self.assertIn('Guardando cambios', self.bar.currentMessage())

    def test_finish_stops_elapsed_and_does_not_restore_stale_progress(self):
        self.bar.begin_progress()
        self.bar.finish_progress()
        self.bar.showMessage('Actualización completada')
        self.bar._render_progress()
        self.assertEqual(self.bar.currentMessage(), 'Actualización completada')
        self.assertFalse(self.bar._timer.isActive())

    def test_priority_pause_and_resume_change_persistent_phase_only_for_update(self):
        self.bar.begin_progress()
        self.bar.handle_job_event({'label':'Actualizar listado de Maximo','kind':'paused'})
        self.assertIn('Pausada', self.bar.currentMessage())
        self.bar.handle_job_event({'label':'Otra tarea','kind':'started'})
        self.assertIn('Pausada', self.bar.currentMessage())
        self.bar.handle_job_event({'label':'Actualizar listado de Maximo','kind':'resumed'})
        self.assertIn('Reanudando', self.bar.currentMessage())

    def test_status_clear_restores_update_but_not_after_failure(self):
        self.bar.begin_progress()
        self.bar.clearMessage()
        self.assertIn('Actualización de Maximo', self.bar.currentMessage())
        self.bar.finish_progress()
        self.bar.showMessage('La actualización falló.')
        self.bar.clearMessage()
        self.assertEqual(self.bar.currentMessage(), '')

    def test_export_reports_real_phases_in_order_and_commits_once(self):
        with temporary_directory() as folder:
            driver=Mock();phases=[]
            with patch.object(updater,'load_config',return_value=Mock(download_dir=folder)), \
                 patch.object(updater,'create_edge_profile',return_value='fake-profile'), \
                 patch.object(updater,'setup_driver',return_value=driver), \
                 patch.object(updater,'login'),patch.object(updater,'open_workorders_app'), \
                 patch.object(updater,'download_file',return_value='download.xls'), \
                 patch.object(updater,'move_downloaded_file',return_value=str(Path(folder)/'export.xls')), \
                 patch.object(updater,'cleanup_edge_profile'),patch.object(updater,'process_html_table',return_value='frame'), \
                 patch.object(updater,'update_database_from_df',return_value=(2,3)) as save, \
                 patch.object(updater,'cleanup_exports'):
                result=updater.run_update(progress_callback=lambda done,total,phase: phases.append(phase))
            self.assertEqual(result,(2,3));save.assert_called_once_with('frame')
            self.assertEqual(phases,['Abriendo Edge (intento 1/2)','Iniciando sesión en Maximo',
                'Abriendo listado de OTs','Esperando exportación y descarga del listado',
                'Preparando archivo descargado','Procesando listado descargado',
                'Guardando cambios en la base de datos','Finalizando actualización'])


class GenericTaskStatusTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.bar=UpdateStatusBar();self.addCleanup(self.bar.deleteLater)

    def event(self,kind,ident='reading',label='Información ampliada'):
        self.bar.handle_job_event({'kind':kind,'id':ident,'label':label})

    def test_settings_notice_restores_latest_progress_of_running_task(self):
        self.event('started')
        self.bar.showMessage('Lectura 1/10 · OT 100')
        self.bar.showMessage('Configuración guardada y aplicada',20)
        self.bar.showMessage('Lectura 2/10 · OT 200')
        self.assertEqual(self.bar.currentMessage(),'Configuración guardada y aplicada')
        QTest.qWait(80)
        self.assertEqual(self.bar.currentMessage(),'Lectura 2/10 · OT 200')

    def test_generic_job_without_explicit_progress_returns_with_elapsed_time(self):
        self.event('started',label='Conciliación de OTs')
        self.bar.showMessage('Búsqueda guardada',20)
        QTest.qWait(80)
        self.assertIn('Conciliación de OTs',self.bar.currentMessage())
        self.assertIn('transcurridos',self.bar.currentMessage())
        self.assertTrue(self.bar._timer.isActive())

    def test_job_finishing_during_notice_is_never_restored(self):
        self.event('started')
        self.bar.showMessage('Leyendo OT 100')
        self.bar.showMessage('Configuración guardada',20)
        self.event('finished')
        QTest.qWait(80)
        self.assertEqual(self.bar.currentMessage(),'')
        self.assertFalse(self.bar._timer.isActive())

    def test_finished_job_result_replaces_progress_under_temporary_notice(self):
        self.event('started')
        self.bar.showMessage('Configuración guardada',20)
        self.event('finished')
        self.bar.showMessage('Información ampliada: 10 campos completados')
        QTest.qWait(80)
        self.assertEqual(self.bar.currentMessage(),'Información ampliada: 10 campos completados')

    def test_priority_job_finishes_then_resumed_job_returns_after_notice(self):
        self.event('started','background','Conciliación de OTs')
        self.bar.showMessage('Conciliación 2/10')
        self.event('paused','background','Conciliación de OTs')
        self.event('started','manual','Actualizar avería')
        self.bar.showMessage('Actualizando avería 1/2')
        self.bar.showMessage('Configuración guardada',20)
        self.event('finished','manual','Actualizar avería')
        self.event('resumed','background','Conciliación de OTs')
        QTest.qWait(80)
        self.assertEqual(self.bar.currentMessage(),'Conciliación 2/10')
        self.event('finished','background','Conciliación de OTs')
        self.assertNotIn('Conciliación 2/10',self.bar.currentMessage())

    def test_idle_summary_survives_temporary_notice(self):
        self.bar.showMessage('Última sincronización: completada')
        self.bar.showMessage('Configuración guardada',20)
        QTest.qWait(80)
        self.assertEqual(self.bar.currentMessage(),'Última sincronización: completada')
