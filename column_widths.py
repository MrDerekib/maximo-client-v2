"""Distinguish user header gestures from automatic Qt/layout section changes."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHeaderView


class ColumnWidthHeader(QHeaderView):
    manualSectionResized = Signal(int, int, int)
    resizeStarted = Signal()
    resizeFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._pointer_down = False
        self._resized = False
        self.sectionResized.connect(self._section_resized)

    def _section_resized(self, index, before, after):
        if self._pointer_down and before != after:
            if not self._resized:
                self.resizeStarted.emit()
            self._resized = True
            self.manualSectionResized.emit(index, before, after)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pointer_down = True
            self._resized = False
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            changed = self._resized
            self._pointer_down = False
            self._resized = False
            if changed:
                self.resizeFinished.emit()
