"""Release notes are local, version-specific and not repeated after a rollback."""
import tests  # Isolate application data before importing product modules.
import io
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import config
from release_notes import (STATE_FILENAME, cache_release_notes, changelog_section, initialize_history,
                           installed_release_notes, mark_notes_seen, should_show_notes)
from tests.test_support import temporary_directory
from update_checker import fetch_latest_release


class ReleaseNotesTests(TestCase):
    def test_fresh_install_does_not_show_a_popup_until_it_is_upgraded(self):
        with temporary_directory() as folder:
            path = Path(folder) / STATE_FILENAME
            initialize_history(path, '1.1.0')
            self.assertFalse(should_show_notes(path, 'v1.1.0'))
            self.assertTrue(should_show_notes(path, '1.1.1'))

    def test_legacy_installation_shows_once_and_rollback_does_not_reset_history(self):
        with temporary_directory() as folder:
            path = Path(folder) / STATE_FILENAME
            self.assertTrue(should_show_notes(path, '1.1.1'))
            mark_notes_seen(path, '1.1.1')
            self.assertFalse(should_show_notes(path, 'v1.1.1'))
            self.assertFalse(should_show_notes(path, '1.1.0'))
            mark_notes_seen(path, '1.1.0')
            self.assertFalse(should_show_notes(path, '1.1.1'))
            self.assertTrue(should_show_notes(path, '1.1.2'))

    def test_cache_survives_restart_and_is_only_used_for_the_installed_version(self):
        with temporary_directory() as folder:
            path = Path(folder) / STATE_FILENAME
            changelog = Path(folder) / 'CHANGELOG.md'
            changelog.write_text('## 1.1.1 — Actual\n\nNotas locales.\n\n## 1.1.0\n\nHistorial antiguo.', encoding='utf-8')
            initialize_history(path, '1.1.0')
            cache_release_notes(path, 'v1.1.1', '## Novedades\n\n- Notas de GitHub.', 'https://example.test/1.1.1')
            self.assertFalse(should_show_notes(path, '1.1.0'))
            self.assertTrue(should_show_notes(path, '1.1.1'))
            notes = installed_release_notes(path, '1.1.1', changelog)
            self.assertEqual(notes.source, 'github')
            self.assertIn('Notas de GitHub', notes.markdown)
            cache_release_notes(path, 'v1.2.0', 'Notas de otra versión.')
            notes = installed_release_notes(path, '1.1.1', changelog)
            self.assertEqual(notes.source, 'changelog')
            self.assertIn('Notas locales', notes.markdown)
            self.assertNotIn('Historial antiguo', notes.markdown)
            self.assertNotIn('otra versión', notes.markdown)
            self.assertTrue(should_show_notes(path, '1.1.1'))

    def test_version_sections_support_revision_and_ignore_other_versions(self):
        text = '# Historial\n## 1.1.2\nNuevo\n## [v1.1.1.2] — Revisión\nActual\n### Detalle\nMás\n## 1.1.1\nAnterior\n'
        section = changelog_section(text, '1.1.1.2')
        self.assertIn('Actual', section)
        self.assertIn('Más', section)
        self.assertNotIn('Nuevo', section)
        self.assertNotIn('Anterior', section)
        self.assertFalse(changelog_section(text, '9.0.0'))

    def test_corrupt_history_can_be_repaired_without_crashing_startup(self):
        with temporary_directory() as folder:
            path = Path(folder) / STATE_FILENAME
            path.write_text('{broken', encoding='utf-8')
            with self.assertLogs(level='WARNING'):
                self.assertTrue(should_show_notes(path, '1.1.1'))
                mark_notes_seen(path, '1.1.1')
            self.assertFalse(should_show_notes(path, '1.1.1'))
            state = json.loads(path.read_text(encoding='utf-8'))
            state['cached_release'] = {'tag': 123, 'markdown': 'bad cache'}
            path.write_text(json.dumps(state), encoding='utf-8')
            self.assertFalse(installed_release_notes(path, '1.1.1', Path(folder)/'missing').markdown)

    def test_empty_cache_does_not_replace_notes_and_initialization_does_not_erase_seen_version(self):
        with temporary_directory() as folder:
            path = Path(folder) / STATE_FILENAME
            mark_notes_seen(path, '1.1.2')
            cache_release_notes(path, 'v1.1.2', 'Notas')
            cache_release_notes(path, 'v1.1.3', '')
            initialize_history(path, '1.0.0')
            self.assertFalse(should_show_notes(path, '1.1.2'))
            self.assertEqual(installed_release_notes(path, '1.1.2').markdown, 'Notas')

    def test_creating_a_new_config_initializes_the_history_beside_it(self):
        with temporary_directory() as folder:
            destination = Path(folder) / 'config.json'
            with patch.object(config, 'CONFIG_PATH', destination), \
                 patch.object(config, 'ensure_user_directories'), patch.object(config, '_migrate_legacy_storage'), \
                 patch.object(config, '_sanitize_legacy_artifacts'), patch.object(config, 'save_config'), \
                 patch.object(config, 'load_credentials', return_value=('', '')):
                config.load_config()
            self.assertFalse(should_show_notes(destination.parent / STATE_FILENAME, config.version.APP_VERSION))

    def test_release_api_preserves_markdown_and_accepts_missing_body(self):
        for body, expected in (('## Cambios\n\n- Mejora.', '## Cambios\n\n- Mejora.'), (None, ''), (123, '')):
            response = io.BytesIO(json.dumps({'tag_name': 'v1.1.1', 'body': body}).encode())
            with self.subTest(body=body), patch('update_checker.urllib.request.urlopen', return_value=response):
                self.assertEqual(fetch_latest_release().notes, expected)
