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
