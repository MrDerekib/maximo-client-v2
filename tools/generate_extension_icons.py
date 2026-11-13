"""Render a single solid-blue M, legible at native toolbar size."""
import os
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

def generate():
    app = QApplication.instance() or QApplication([])
    destination = Path(__file__).resolve().parents[1] / "browser_extension" / "icons"
    destination.mkdir(exist_ok=True)
    for size in (16, 24, 32, 48, 128):
        # Supersample the small toolbar sizes for crisp rounded corners/text.
        scale = 4
        image = QImage(size*scale, size*scale, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#176fc9"))
        # Pixel-aligned silhouette on a 16px grid. No tiny text or enclosing tile.
        painter.scale(size*scale/16, size*scale/16)
        mark = QPainterPath()
        mark.moveTo(2,14)
        for x,y in ((2,2),(5,2),(8,7.5),(11,2),(14,2),(14,14),
                    (11,14),(11,7.5),(8,12),(5,7.5),(5,14)):
            mark.lineTo(x,y)
        mark.closeSubpath()
        painter.drawPath(mark)
        painter.end()
        icon = image.scaled(size,size,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        if not icon.save(str(destination/f"md-{size}.png")): raise RuntimeError("Could not write extension icon")

if __name__ == "__main__": generate()
