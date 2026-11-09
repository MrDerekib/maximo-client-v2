import tests  # Isolate application data before importing product modules.
import json
import tempfile
from unittest import TestCase
from warehouse_diagnostics import sanitize, WarehouseJournal


class DiagnosticTests(TestCase):
    def test_credentials_notes_and_url_session_values_are_not_logged(self):
        data=sanitize({'password':'secret_password','details':'private_note',
            'nested':{'cookie':'cookie_value'},
            'message':'Failed https://user:password@example.com/maximo/ui/?uisessionid=secret_session&csrftoken=secret_token token=hidden'})
        serialized=json.dumps(data)
        for secret in ('secret_password','private_note','cookie_value','secret_session','secret_token','hidden','user:password'):
            self.assertNotIn(secret,serialized)
        self.assertIn('https://example.com/maximo/ui/',serialized)

    def test_every_event_has_correlation_sequence_and_timestamp(self):
        with tempfile.TemporaryFile(mode='w+',encoding='utf-8') as stream:
            journal=WarehouseJournal(stream,'batch-123')
            journal({'event':'ot_started','ot':'1'})
            journal({'event':'ot_error','ot':'1','password':'hidden'})
            stream.seek(0)
            rows=[json.loads(line) for line in stream]
        self.assertEqual([r['sequence'] for r in rows],[1,2])
        self.assertTrue(all(r['batch_id']=='batch-123' and r['at'] and r['schema_version']==2 for r in rows))
        self.assertEqual(rows[1]['password'],'[REDACTED]')
