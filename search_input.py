"""Paste a column directly into the existing comma-separated search."""
import re
from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QLineEdit


def normalize_pasted_search(text):
    """Rows/cells are OR alternatives; spaces inside a value remain AND terms."""
    values = []
    seen = set()
    for part in re.split(r'[,\r\n\t\u2028\u2029]+', text):
        value = ' '.join(part.split())
        if value and value.casefold() not in seen:
            values.append(value)
            seen.add(value.casefold())
    return ', '.join(values)


class SearchLineEdit(QLineEdit):
    pasted = Signal()

    def paste(self):
        if self.isReadOnly() or not self.isEnabled():
            return
        text = normalize_pasted_search(QApplication.clipboard().text())
        if not text:
            return
        self.insert(text)
        self.pasted.emit()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste):
            self.paste()
            event.accept()
            return
        super().keyPressEvent(event)

    def createStandardContextMenu(self):
        menu = super().createStandardContextMenu()
        for action in menu.actions():
            if action.objectName() == 'edit-paste':
                action.triggered.disconnect()
                action.triggered.connect(self.paste)
                break
        return menu

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        try:
            menu.exec(event.globalPos())
        finally:
            menu.deleteLater()
