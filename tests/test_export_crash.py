"""Read-only export recovery never repeats an OT action or commits partial data."""
import tests
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
from selenium.common.exceptions import WebDriverException
from tests.test_support import temporary_directory
import updater
import maximo_client as client


class ExportCrashTests(TestCase):
    def run_export(self,login_errors,*,quit_error=False):
        with temporary_directory() as folder,ExitStack() as stack:
            stack.enter_context(patch.object(updater,'load_config',return_value=SimpleNamespace(download_dir=folder)))
            stack.enter_context(patch.object(client,'EDGE_PROFILE_DIR',Path(folder)/'profiles'))
            drivers=[Mock(),Mock()]
            if quit_error:drivers[0].quit.side_effect=WebDriverException('invalid session id')
            setup=stack.enter_context(patch.object(updater,'setup_driver',side_effect=drivers))
            stack.enter_context(patch.object(updater,'login',side_effect=login_errors))
            stack.enter_context(patch.object(updater,'open_workorders_app'))
            download=stack.enter_context(patch.object(updater,'download_file',return_value='export.xls'))
            stack.enter_context(patch.object(updater,'move_downloaded_file',return_value=str(Path(folder)/'export.xls')))
            stack.enter_context(patch.object(updater,'process_html_table',return_value='frame'))
            save=stack.enter_context(patch.object(updater,'update_database_from_df',return_value=(1,2)))
            stack.enter_context(patch.object(updater,'cleanup_exports'))
            phases=[]
            try:
                result=updater.run_update(progress_callback=lambda _done,_total,phase:phases.append(phase))
            except Exception as exc:result=exc
            for call in setup.call_args_list:
                self.assertFalse(Path(call.kwargs['profile_dir']).exists())
                self.assertFalse(Path(call.kwargs['download_dir']).exists())
            for driver in drivers[:setup.call_count]:driver.quit.assert_called_once()
            return result,setup.call_count,download.call_count,save,phases,setup.call_args_list

    def test_crash_during_login_recovers_once_in_new_session_and_commits_once(self):
        result,attempts,downloads,save,phases,calls=self.run_export([WebDriverException('tab crashed'),None])
        self.assertEqual(result,(1,2));self.assertEqual(attempts,2);self.assertEqual(downloads,1)
        save.assert_called_once_with('frame')
        self.assertNotEqual(calls[0].kwargs['profile_dir'],calls[1].kwargs['profile_dir'])
        self.assertTrue(any('reintentando' in phase for phase in phases))

    def test_two_crashes_stop_without_database_changes(self):
        result,attempts,downloads,save,*_=self.run_export([WebDriverException('tab crashed')]*2)
        self.assertIsInstance(result,RuntimeError);self.assertIn('antes de guardar datos',str(result))
        self.assertEqual(attempts,2);self.assertEqual(downloads,0);save.assert_not_called()

    def test_other_webdriver_errors_and_validation_errors_are_not_retried(self):
        for error in (WebDriverException('element click intercepted'),RuntimeError('Credenciales no válidas')):
            result,attempts,_,save,*_=self.run_export([error])
            self.assertIs(result,error);self.assertEqual(attempts,1);save.assert_not_called()

    def test_quit_error_does_not_hide_original_crash_or_prevent_retry(self):
        result,attempts,_,save,*_=self.run_export([WebDriverException('tab crashed'),None],quit_error=True)
        self.assertEqual(result,(1,2));self.assertEqual(attempts,2);save.assert_called_once()
