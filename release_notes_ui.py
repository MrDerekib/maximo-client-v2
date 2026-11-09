"""One-version changelog viewer; Markdown cannot load external resources."""
import webbrowser
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout


class NotesBrowser(QTextBrowser):
    def loadResource(self, resource_type, name):
        return None


class ReleaseNotesDialog(QDialog):
    def __init__(self, notes, parent=None, colors=None):
        super().__init__(parent)
        colors = colors or {'text': '#172033', 'heading': '#102a43', 'surface': '#ffffff',
                            'border': '#d9e2ec', 'muted': '#627d98'}
        self.setWindowTitle(f'Novedades de Maximo Desktop {notes.version}')
        self.setWindowModality(Qt.WindowModal)
        self.resize(740, 520)
        self.setMinimumSize(540, 400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = QLabel(f'Maximo Desktop {notes.version}')
        title.setStyleSheet(f'font-size: 22px; font-weight: 700; color: {colors["heading"]}')
        subtitle = QLabel('Estas son las novedades de la versión instalada. Este aviso se muestra una sola vez.')
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f'color: {colors["muted"]}')
        layout.addWidget(title); layout.addWidget(subtitle)
        self.browser = NotesBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(self._open_link)
        self.browser.setStyleSheet(f'QTextBrowser {{ background: {colors["surface"]}; color: {colors["text"]}; '
                                  f'border: 1px solid {colors["border"]}; border-radius: 8px; padding: 12px; }}')
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
