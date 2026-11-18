"""A rounded outer frame clips opaque table headers/selection gutter as well."""
from PySide6.QtCore import QEvent,QRectF
from PySide6.QtGui import QPainterPath,QRegion
from PySide6.QtWidgets import QFrame,QVBoxLayout


class RoundedTableFrame(QFrame):
    def __init__(self,table,parent=None):
        super().__init__(parent)
        self.setObjectName('roundedTableFrame')
        self.table=table;table.setObjectName('roundedTable')
        layout=QVBoxLayout(self);layout.setContentsMargins(1,1,1,1);layout.setSpacing(0)
        layout.addWidget(table)
        table.installEventFilter(self)
        self._clip_table()

    def _clip_table(self):
        rect=self.table.rect()
        if rect.isEmpty():return
        path=QPainterPath();path.addRoundedRect(QRectF(rect),7,7)
        self.table.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def eventFilter(self,watched,event):
        if watched is self.table and event.type() in (QEvent.Resize,QEvent.Show):self._clip_table()
        return False
