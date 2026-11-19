"""Version-aware changelog viewer; Markdown cannot load external resources."""
import webbrowser
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout


class NotesBrowser(QTextBrowser):
    def loadResource(self, resource_type, name):
        return None


class ReleaseNotesDialog(QDialog):
    def __init__(self, notes, parent=None, colors=None):
        super().__init__(parent)
        self.setWindowTitle(f'Novedades de Maximo Desktop {notes.version}')
        self.setWindowModality(Qt.WindowModal)
        self.resize(740, 520)
        self.setMinimumSize(540, 400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = QLabel(f'Maximo Desktop {notes.version}')
        title.setObjectName("releaseNotesTitle")
        subtitle = QLabel(
            f'Novedades desde {notes.from_version} hasta {notes.version}. Este aviso se muestra una sola vez.'
            if notes.from_version else
            'Estas son las novedades de la versión instalada. Este aviso se muestra una sola vez.')
        subtitle.setWordWrap(True)
        subtitle.setObjectName("filterHint")
        layout.addWidget(title); layout.addWidget(subtitle)
        self.browser = NotesBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(self._open_link)
        self.browser.setMarkdown(notes.markdown)
        layout.addWidget(self.browser, 1)
        buttons = QHBoxLayout()
        if notes.url.startswith(('https://', 'http://')):
            release = QPushButton('Ver todos los cambios', objectName='fullReleaseNotes')
            release.clicked.connect(lambda: webbrowser.open(notes.url))
            buttons.addWidget(release)
        buttons.addStretch()
        close = QPushButton('Entendido', objectName='primary')
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    @staticmethod
    def _open_link(url):
        if url.scheme().lower() in ('http', 'https'):
            webbrowser.open(url.toString())
