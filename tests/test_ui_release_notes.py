from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from PySide6.QtCore import QUrl
from release_notes import ReleaseNotes
from release_notes_ui import NotesBrowser, ReleaseNotesDialog
from tests.test_ui_app_updates import QApplication, MaximoDesktopWindow
from tests.test_support import temporary_directory


class ReleaseNotesUiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self):
        return SimpleNamespace(_closing=False, cfg=SimpleNamespace(latest_release_tag='v1.1.1',
                               latest_release_url='https://example.test/v1.1.1'))

    def test_after_update_shows_only_once_even_if_called_again(self):
        with temporary_directory() as folder:
            config = Path(folder) / 'config.json'
            notes = ReleaseNotes('v1.1.1', '- Mejora.', source='github')
            dialog = Mock()
            with patch('ui_qt.CONFIG_PATH', config), patch('ui_qt.DEVELOPMENT_MODE', False), \
                 patch('ui_qt.distributed_executable', return_value=Path('MaximoDesktop.exe')), \
                 patch('ui_qt.version.APP_VERSION', '1.1.1'), \
                 patch('ui_qt.installed_release_notes', return_value=notes), \
                 patch('ui_qt.ReleaseNotesDialog', return_value=dialog) as create:
                window = self.window()
                MaximoDesktopWindow._show_installed_release_notes(window)
                MaximoDesktopWindow._show_installed_release_notes(window)
            create.assert_called_once()
            dialog.exec.assert_called_once()

    def test_python_and_development_runs_do_not_consume_or_show_notes(self):
        for development, executable in ((True, Path('MaximoDesktop.exe')), (False, None)):
            with self.subTest(development=development), patch('ui_qt.DEVELOPMENT_MODE', development), \
                 patch('ui_qt.distributed_executable', return_value=executable), \
                 patch('ui_qt.should_show_notes') as history, patch('ui_qt.ReleaseNotesDialog') as create:
                MaximoDesktopWindow._show_installed_release_notes(self.window())
                history.assert_not_called(); create.assert_not_called()

    def test_startup_shows_notes_before_checking_for_the_next_release(self):
        calls = []
        window = SimpleNamespace(_closing=False, _show_installed_release_notes=lambda: calls.append('notes'),
                                 check_app_updates=lambda **kw: calls.append('check'))
        MaximoDesktopWindow._startup_release_updates(window)
        self.assertEqual(calls, ['notes', 'check'])
        window._show_installed_release_notes = Mock(side_effect=RuntimeError('notes failure'))
        with self.assertLogs(level='ERROR'):
            MaximoDesktopWindow._startup_release_updates(window)
        self.assertEqual(calls, ['notes', 'check', 'check'])

    def test_markdown_is_displayed_but_external_resources_and_local_links_are_blocked(self):
        dialog = ReleaseNotesDialog(ReleaseNotes('v1.1.1', '## Cambios\n\n- Mejora de impresión.'))
        try:
            self.assertIn('Mejora de impresión', dialog.browser.toPlainText())
            self.assertIsNone(dialog.browser.loadResource(2, QUrl('file:///private/image.png')))
            self.assertIsNone(dialog.browser.loadResource(2, QUrl('https://example.test/image.png')))
            with patch('release_notes_ui.webbrowser.open') as open_url:
                dialog._open_link(QUrl('file:///private/file'))
                open_url.assert_not_called()
                dialog._open_link(QUrl('https://github.com/example/release'))
                open_url.assert_called_once()
        finally:
            dialog.deleteLater(); self.app.processEvents()
