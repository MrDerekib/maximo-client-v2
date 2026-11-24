"""Lightweight refresh animation; no timer runs while the listing is idle."""
from PySide6.QtCore import QEvent, QObject, QElapsedTimer, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy


class RefreshIcon(QObject):
    def __init__(self,button,asset,color):
        super().__init__(button);self.button=button;self.asset=asset;self.running=False;self.angle=0
        self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self._frame)
        self.elapsed=QElapsedTimer();self.set_color(color)

    def set_color(self,color):
        self.source=QIcon(str(self.asset)).pixmap(40,40)
        painter=QPainter(self.source);painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(self.source.rect(),QColor(color));painter.end();self._render()

    def set_running(self,running):
        running=bool(running)
        if running==self.running:return
        self.running=running
        if running:self.elapsed.start();self.timer.start()
        else:self.timer.stop();self.angle=0
        self._render()

    def _frame(self):
        # The SVG arrows point counterclockwise; Qt positive angles rotate clockwise.
        self.angle=-(self.elapsed.elapsed()%1200)*360/1200
        if self.button.isVisible():self._render()

    def _render(self):
        canvas=QPixmap(44,44);canvas.fill(Qt.transparent)
        painter=QPainter(canvas);painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.translate(22,22);painter.rotate(self.angle)
        painter.drawPixmap(QRectF(-18,-18,36,36),self.source,QRectF(self.source.rect()));painter.end()
        canvas.setDevicePixelRatio(2)
        if isinstance(self.button, QLabel):
            self.button.setPixmap(canvas)
        else:
            self.button.setIcon(QIcon(canvas))


class RefreshIndicator(QLabel):
    """Use the same spinner as the listing, tinted for a text surface."""

    def __init__(self, asset, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.animation = RefreshIcon(self, asset, self.palette().color(QPalette.WindowText))
        self.hide()

    def set_running(self, running):
        self.animation.set_running(running)
        self.setVisible(running)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange and hasattr(self, 'animation'):
            self.animation.set_color(self.palette().color(QPalette.WindowText))


def set_list_update_busy(window,busy):
    window._list_update_pending=busy
    icon=getattr(window,'update_icon',None)
    if icon is not None:icon.set_running(busy)
