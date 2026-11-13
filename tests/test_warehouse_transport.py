import tests  # Isolate application data before importing product modules.
from threading import Event
from unittest import TestCase
from unittest.mock import Mock, patch
from pathlib import Path
from itertools import count
from tests.test_support import temporary_directory
from warehouse_recovery import RecoveryStore

from warehouse import WarehouseItem
from warehouse_transport import run_live, unique_caption
from config import AppConfig


def single_pass(*args, **kwargs):
    """Existing transport assertions inspect only execution; recovery has its own suite."""
    return run_live(*args, auto_recheck=False, **kwargs)


class TransportTests(TestCase):
    def setUp(self):
        temp=temporary_directory();self.folder=Path(temp.__enter__())
        self.addCleanup(temp.__exit__,None,None,None)
        sequence=count()
        patcher=patch('warehouse_transport.default_recovery_store',side_effect=lambda:RecoveryStore(self.folder/str(next(sequence))))
        patcher.start();self.addCleanup(patcher.stop)

    def test_details_preference_missing_or_invalid_stays_disabled(self):
        self.assertFalse(AppConfig().warehouse_ask_sat_details)
        for value in ('true', 'false', 1, None):
            self.assertFalse(AppConfig(warehouse_ask_sat_details=value).warehouse_ask_sat_details)
        self.assertTrue(AppConfig(warehouse_ask_sat_details=True).warehouse_ask_sat_details)
    def session(self, state='WAPPR'):
        s = Mock()
        s.open.return_value = state
        s.identity.return_value = {'Activo': '123', 'Nº de serie': 'ABC', 'Planta': 'LAB-BAD'}
        s.choice.return_value = {'id': 'dynamic', 'checked': True}
        s.verify.side_effect = lambda ot, state, identity: state
        return s

    def test_caption_rejects_missing_ambiguous_and_disabled(self):
        option = {'caption': 'Confirmar recepción', 'disabled': False}
        for options in ([], [option, option], [{**option, 'disabled': True}]):
            with self.assertRaises(RuntimeError):
                unique_caption(options, 'Confirmar recepción')
        self.assertEqual(unique_caption([option], 'confirmar recepcion'), option)

    def test_server_state_blocks_route_even_when_local_state_is_eligible(self):
        s = self.session('CLOSE')
        r = single_pass([WarehouseItem('1', status='PDTE CONFIRMAR')], 'receive', session_factory=lambda:s)
        self.assertEqual(r[0].status, 'failed')
        s.driver.find_element.assert_not_called()
        s.accept_button.assert_not_called()

    def test_unvalidated_actions_never_create_browser(self):
        factory = Mock()
        for action in ('reject_receive',):
            with self.assertRaises(ValueError):
                single_pass([WarehouseItem('1')], action, session_factory=factory)
        factory.assert_not_called()

    def test_sat_variants_require_their_own_new_history_entry_and_keep_details(self):
        for action in ('receive_sat_external', 'receive_sat_internal'):
            for text in ('', 'Detalle aprobado'):
                s = self.session()
                s.history_count.side_effect = [0, 1]
                r = single_pass([WarehouseItem('1')], action, details={'1': text}, session_factory=lambda:s)
                self.assertEqual(r[0].status, 'success')
                s.sat_details.assert_called_once()
                self.assertEqual(s.sat_details.call_args.args[:2], (action,text))
                s.verify.assert_called_once_with('1','ISSUE',s.identity.return_value)
                self.assertEqual(s.history_count.call_args_list[0].args, s.history_count.call_args_list[1].args)

    def test_sat_issue_without_new_history_is_uncertain(self):
        s = self.session()
        s.history_count.side_effect = [2, 2]
        r = single_pass([WarehouseItem('1')], 'receive_sat_external', session_factory=lambda:s)
        self.assertEqual(r[0].status, 'uncertain')
        s.accept_button.return_value.click.assert_called_once()

    def test_sat_details_failure_never_repeats_first_confirmation(self):
        s = self.session()
        s.history_count.return_value=0
        s.sat_details.side_effect=RuntimeError('Otro diálogo')
        r=single_pass([WarehouseItem('1')], 'receive_sat_internal', session_factory=lambda:s)
        self.assertEqual(r[0].status, 'uncertain')
        s.accept_button.return_value.click.assert_called_once()
        s.sat_details.assert_called_once()

    def test_confirmation_is_journaled_before_click_and_verified_afterwards(self):
        s = self.session()
        entries = []
        s.accept_button.return_value.click.side_effect = lambda: self.assertEqual(entries[-1]['confirmation'], 'sending_once')
        r = single_pass([WarehouseItem('1')], 'receive', journal=entries.append, session_factory=lambda:s)
        self.assertEqual(r[0].status, 'success')
        s.accept_button.return_value.click.assert_called_once()
        s.verify.assert_called_once_with('1', 'APPR', s.identity.return_value)
        s.close.assert_called_once()

    def test_uncertain_submission_is_not_retried_and_next_ot_uses_new_session(self):
        first, second = self.session(), self.session()
        first.accept_button.return_value.click.side_effect = TimeoutError('lost response')
        factory = Mock(side_effect=[first, second])
        results = single_pass([WarehouseItem('1'), WarehouseItem('2')], 'receive', session_factory=factory)
        self.assertEqual([r.status for r in results], ['uncertain', 'success'])
        first.accept_button.return_value.click.assert_called_once()
        first.close.assert_called_once()
        self.assertEqual(factory.call_count, 2)

    def test_stop_after_current_ot_does_not_submit_next(self):
        stop, s = Event(), self.session()
        def progress(index, result):
            if result.status == 'success':
                stop.set()
        r = single_pass([WarehouseItem('1'), WarehouseItem('2')], 'receive',
                     stop=stop, progress=progress, session_factory=lambda:s)
        self.assertEqual([x.status for x in r], ['success', 'stopped'])
        s.accept_button.return_value.click.assert_called_once()

    def test_failed_verification_does_not_claim_success(self):
        s = self.session()
        s.verify.side_effect = RuntimeError('Unexpected dialog')
        r = single_pass([WarehouseItem('1')], 'receive', session_factory=lambda:s)
        self.assertEqual(r[0].status, 'uncertain')
        s.accept_button.return_value.click.assert_called_once()

    def test_error_diagnostics_include_stage_context_and_submission_flag(self):
        s=self.session()
        s.verify.side_effect=RuntimeError('BMXAA9999E unexpected dialog')
        s.diagnostic_context.return_value={'ui':{'dialogs':[{'id':'unexpected','text':'BMXAA9999E'}]}}
        entries=[]
        r=single_pass([WarehouseItem('1')],'receive',session_factory=lambda:s,journal=entries.append)
        error=next(e for e in entries if e.get('event')=='ot_error')
        self.assertEqual(error['step'],'Verificar resultado')
        self.assertTrue(error['confirmation_attempted'])
        self.assertEqual(error['maximo_codes'],['BMXAA9999E'])
        self.assertIn('unexpected',str(error['context']))
        self.assertTrue(error['traceback'])
        self.assertEqual(r[0].status,'uncertain')

    def test_journal_failure_before_confirmation_prevents_click_and_closes_session(self):
        s=self.session()
        def journal(entry):
            if entry.get('confirmation')=='sending_once':
                raise OSError('Log disk unavailable')
        r=single_pass([WarehouseItem('1')],'receive',session_factory=lambda:s,journal=journal)
        s.accept_button.return_value.click.assert_not_called()
        s.close.assert_called_once()
        self.assertEqual(r[0].status,'uncertain')

    def test_session_is_closed_even_if_error_diagnostics_cannot_be_written(self):
        s=self.session()
        s.verify.side_effect=RuntimeError('Lost response')
        def journal(entry):
            if entry.get('event')=='ot_error':
                raise OSError('Disk unavailable')
        with self.assertRaises(OSError):
            single_pass([WarehouseItem('1')],'receive',session_factory=lambda:s,journal=journal)
        s.close.assert_called_once()
        s.accept_button.return_value.click.assert_called_once()
