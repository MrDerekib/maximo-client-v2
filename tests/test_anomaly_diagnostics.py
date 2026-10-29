import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import anomaly_diagnostics as diagnostics
import workorder_start as workflow
from tests.test_support import temporary_directory


class AnomalyDiagnosticsTests(TestCase):
    def setUp(self):
        self.folder = temporary_directory()
        self.root = Path(self.folder.__enter__())
        self.addCleanup(self.folder.__exit__, None, None, None)
        self.patcher = patch.object(diagnostics, 'LOG_DIR', self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.context = {'ot': '3088915', 'mode': 'configured', 'stage': 'code_filter',
                        'requested': {'class_code': 'RFN-70', 'path': [{'type': 'PROBLEM', 'code': 'OTROS-01'}]},
                        'expected': {'type': 'CAUSE', 'code': 'OTROS-02'}}

    def events(self):
        return [json.loads(line) for line in (self.root / 'anomalias_incidencias.jsonl').read_text(encoding='utf-8').splitlines()]

    def test_keeps_requested_route_options_duplicates_and_partial_pagination(self):
        row = {'code': 'C-RFN-062', 'type': 'CAUSE', 'description': 'VOLUMEN BAJO'}
        snapshots = [{'kind': 'failure_selector', 'filter': '', 'options': [row, row],
                      'pagination': {'first': 1, 'last': 2, 'total': 4}, 'complete': True},
                     {'kind': 'failure_selector', 'filter': '=OTROS-02', 'options': [],
                      'pagination': {'first': 0, 'last': 0, 'total': 0}, 'complete': True}]
        result = diagnostics.record_anomaly_incident(self.context, snapshots, RuntimeError('No existe la opción'))
        event = self.events()[0]
        self.assertEqual(result['id'], event['id'])
        self.assertEqual(event['requested'], self.context['requested'])
        self.assertEqual(event['error']['type'], 'RuntimeError')
        self.assertEqual(event['snapshots'][0]['options'], [row, row])
        self.assertFalse(event['snapshots'][0]['complete'])
        self.assertEqual(event['snapshots'][1]['options'], [])
        self.assertTrue(event['snapshots'][1]['complete'])

    def test_whitelist_and_error_redaction(self):
        self.context['cookies'] = 'do-not-save'
        self.context['requested']['password'] = 'do-not-save'
        snapshots = [{'options': [{'code': 'OTROS-01', 'html': 'do-not-save', 'cookie': 'do-not-save'}]}]
        diagnostics.record_anomaly_incident(self.context, snapshots,
            RuntimeError('https://example.test/?uisessionid=secret password=hidden token=private Stacktrace: private-stack'))
        raw = (self.root / 'anomalias_incidencias.jsonl').read_text(encoding='utf-8')
        for secret in ('do-not-save', 'https://', 'secret', 'hidden', 'private', 'Stacktrace:'):
            self.assertNotIn(secret, raw)

    def test_unknown_pagination_cannot_be_complete(self):
        diagnostics.record_anomaly_incident(self.context, [{'options': [], 'complete': True}], ValueError('x'))
        self.assertFalse(self.events()[0]['snapshots'][0]['complete'])

    def test_pagination_does_not_hide_unobserved_options(self):
        diagnostics.record_anomaly_incident(self.context,
            [{'options': [{'code': 'A'}], 'complete': True, 'pagination': {'first': 1, 'last': 3, 'total': 3}}],
            ValueError('x'))
        self.assertFalse(self.events()[0]['snapshots'][0]['complete'])

    def test_caps_snapshots_and_total_options_and_marks_truncation(self):
        snapshots = [{'options': [{'code': str(index)} for index in range(250)], 'complete': True,
                      'pagination': {'first': 1, 'last': 250, 'total': 250}} for _ in range(15)]
        diagnostics.record_anomaly_incident(self.context, snapshots, ValueError('x'))
        event = self.events()[0]
        self.assertTrue(event['snapshots_truncated'])
        self.assertEqual(len(event['snapshots']), 12)
        self.assertEqual(sum(len(s['options']) for s in event['snapshots']), 200)
        self.assertTrue(all(s['truncated'] and not s['complete'] for s in event['snapshots']))

    def test_rotation_is_bounded(self):
        with patch.object(diagnostics, 'MAX_BYTES', 700):
            for _ in range(20):
                diagnostics.record_anomaly_incident(self.context, [], ValueError('x' * 500))
        files = list(self.root.glob('anomalias_incidencias.jsonl*'))
        self.assertEqual(len(files), 4)
        for file in files:
            for line in file.read_text(encoding='utf-8').splitlines():
                self.assertEqual(json.loads(line)['schema_version'], 1)

    def test_concurrent_lines_are_parseable(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: diagnostics.record_anomaly_incident(self.context, [], ValueError('á')), range(24)))
        self.assertEqual(len(self.events()), 24)
        self.assertEqual(len({result['id'] for result in results}), 24)

    def test_write_failure_does_not_raise(self):
        with patch.object(Path, 'mkdir', side_effect=OSError('disk unavailable')):
            self.assertIsNone(diagnostics.record_anomaly_incident(self.context, [], ValueError('original')))

    def test_only_mode_does_not_create_a_file(self):
        self.context['mode'] = 'only'
        self.assertIsNone(diagnostics.record_anomaly_incident(self.context, [], ValueError('x')))
        self.assertEqual(list(self.root.iterdir()), [])


class DiagnosticWorkflowTests(TestCase):
    def starter(self):
        from unittest.mock import Mock
        starter = workflow.WorkorderStarter(Mock(), '3088915')
        starter.check_location = Mock()
        starter.wait = Mock()
        starter.check_ot = Mock()
        starter.value = Mock(return_value='APPR')
        starter.dialogs = Mock(return_value=[])
        starter.tab = Mock()
        starter.route = Mock()
        return starter

    def test_invalid_saved_selection_is_recorded_before_navigation(self):
        starter = self.starter()
        with patch.object(workflow, 'WorkorderStarter', return_value=starter), \
             patch.object(workflow, 'record_anomaly_incident') as record:
            with self.assertRaises(ValueError):
                workflow.start_workorder(starter.driver, starter.ot, anomaly_selection={})
        starter.tab.assert_not_called()
        starter.route.assert_not_called()
        self.assertEqual(record.call_count, 1)
        self.assertEqual(record.call_args.args[0]['stage'], 'selection_validation')
        self.assertIsInstance(record.call_args.args[2], ValueError)

    def test_writer_failure_preserves_original_error(self):
        starter = self.starter()
        original = ValueError('invalid route')
        with patch.object(workflow, 'WorkorderStarter', return_value=starter), \
             patch.object(workflow, 'resolve_selection', side_effect=original), \
             patch.object(workflow, 'record_anomaly_incident', side_effect=OSError('disk')):
            with self.assertRaises(ValueError) as raised:
                workflow.start_workorder(starter.driver, starter.ot, anomaly_selection={})
        self.assertIs(raised.exception, original)
        starter.route.assert_not_called()

    def test_successful_only_mode_has_no_registry(self):
        starter = self.starter()
        with patch.object(workflow, 'WorkorderStarter', return_value=starter), \
             patch.object(workflow, 'record_anomaly_incident') as record:
            result = workflow.start_workorder(starter.driver, starter.ot, anomaly_mode='only')
        self.assertEqual(result['status'], 'INPRG')
        record.assert_not_called()

    def test_cached_snapshots_survive_dialog_disappearance_and_deduplicate(self):
        starter = self.starter()
        starter.begin_anomaly_diagnostics('configured', {})
        starter.driver.execute_script.return_value = {'rows': [{'code': 'A', 'type': 'CAUSE', 'description': 'á'}],
                                                    'filter': '', 'pagination': {'first': 1, 'last': 1, 'total': 3}}
        starter.failure_selector_state()
        starter.failure_selector_state()
        starter.driver.execute_script.return_value = None
        self.assertIsNone(starter.failure_selector_state())
        self.assertEqual(len(starter.anomaly_diagnostic_snapshots), 1)
        with patch.object(workflow, 'record_anomaly_incident') as record:
            starter.record_anomaly_failure(RuntimeError('selector cerrado'))
        self.assertEqual(record.call_args.args[1][0]['options'][0]['code'], 'A')
