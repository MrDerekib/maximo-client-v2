"""Persistent list-update status underneath temporary foreground notices."""
import time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QStatusBar


class UpdateStatusBar(QStatusBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._update_started = None
        self._phase = ''
        self._own_message = ''
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._render_progress)
        self.messageChanged.connect(self._message_changed)

    def showMessage(self, message, timeout=0):
        if self._update_started is not None and message != self._own_message and not timeout:
            timeout = 7000
        super().showMessage(message, timeout)

    def begin_progress(self):
        self._update_started = time.monotonic()
        self._phase = 'Preparando actualización'
        self._own_message = self.currentMessage()
        self._timer.start()
        self._render_progress()

    def update_progress(self, phase):
        if self._update_started is not None:
            self._phase = phase
            self._render_progress()

    def finish_progress(self):
        self._update_started = None
        self._timer.stop()
        if self.currentMessage() == self._own_message:
            self.clearMessage()
        self._own_message = ''

    def _message_changed(self, message):
        if not message:
            self._render_progress()

    def _render_progress(self):
        if self._update_started is None:
            return
        current = self.currentMessage()
        if current and current != self._own_message:
            return  # Never overwrite another visible notification.
        elapsed = max(0, int(time.monotonic() - self._update_started))
        self._own_message = f'Actualización de Maximo · {self._phase} · {elapsed // 60:02d}:{elapsed % 60:02d} transcurridos'
        self.showMessage(self._own_message)

    def handle_job_event(self, event):
        if event.get('label') != 'Actualizar listado de Maximo':
            return
        phases = {'waiting': 'En espera de otra tarea', 'paused': 'Pausada por una acción prioritaria',
                  'started': 'Preparando sesión', 'resumed': 'Reanudando actualización'}
        if event.get('kind') in phases:
            self.update_progress(phases[event['kind']])
