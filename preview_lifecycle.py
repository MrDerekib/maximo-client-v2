"""Close read-only previews immediately while retaining their live Qt thread."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


def cancel_readonly_preview(dialog, worker):
    if worker is None or not worker.isRunning():
        return False
    dialog._preview_closed = True
    worker.stop_requested.set()
    dialog.setAttribute(Qt.WA_DeleteOnClose, False)
    app = QApplication.instance()
    retained = getattr(app, '_md_cancelled_previews', None)
    if retained is None:
        retained = app._md_cancelled_previews = set()
    if dialog not in retained:
        retained.add(dialog)
        worker.finished.connect(lambda: retained.discard(dialog))
    if not worker.isRunning():
        retained.discard(dialog)
    dialog.hide()
    return True
