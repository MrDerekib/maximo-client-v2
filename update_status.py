"""Task progress survives temporary UI notices without resurrecting finished jobs."""
import time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QStatusBar


class UpdateStatusBar(QStatusBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._update_started = None
        self._phase = ''
        self._own_message = ''
        self._baseline = ''
        self._notice_active = False
        self._jobs = {}
        self._active_job = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._render_progress)
        self.messageChanged.connect(self._message_changed)

    def _sync_timer(self):
        if self._update_started is not None or self._jobs:
            self._timer.start()
        else:
            self._timer.stop()

    def showMessage(self, message, timeout=0):
        message = str(message)
        if not message:
            self.clearMessage()
            return
        job = self._jobs.get(self._active_job)
        list_job = job and job['label'] == 'Actualizar listado de Maximo'
        if self._update_started is not None and (job is None or list_job) and message != self._own_message and not timeout:
            timeout = 7000
        if timeout:
            self._notice_active = True
            super().showMessage(message, timeout)
            return
        if job is not None:
            job['progress'] = message
        else:
            self._baseline = message
        if not self._notice_active:
            self._show_owned(message)

    def clearMessage(self):
        # An explicit clear discards idle text; active tasks are still recoverable.
        self._baseline = ''
        self._notice_active = False
        super().clearMessage()
        self._render_progress()

    def _show_owned(self, message):
        self._own_message = message
        super().showMessage(message)

    def begin_progress(self):
        self._update_started = time.monotonic()
        self._phase = 'Preparando actualización'
        self._baseline = ''
        self._own_message = self.currentMessage()
        self._sync_timer()
        self._render_progress()

    def update_progress(self, phase):
        if self._update_started is not None:
            self._phase = phase
            self._render_progress()

    def finish_progress(self):
        self._update_started = None
        self._sync_timer()
        if not self._notice_active:
            self._render_progress()

    def _message_changed(self, message):
        if not message:
            self._notice_active = False
            self._render_progress()

    def _render_progress(self):
        if self._notice_active:
            return
        current = self.currentMessage()
        if current and current != self._own_message:
            return
        job = self._jobs.get(self._active_job)
        if job is not None and job['label'] != 'Actualizar listado de Maximo':
            elapsed = max(0, int(time.monotonic() - job['started']))
            message = job.get('progress') or f"{job['label']} · En curso · {elapsed // 60:02d}:{elapsed % 60:02d} transcurridos"
        elif self._update_started is not None:
            elapsed = max(0, int(time.monotonic() - self._update_started))
            message = f'Actualización de Maximo · {self._phase} · {elapsed // 60:02d}:{elapsed % 60:02d} transcurridos'
        elif job is not None:
            message = job.get('progress') or job['label'] + ' · En curso'
        else:
            paused = [item for item in self._jobs.values() if item.get('paused')]
            message = paused[-1]['label'] + ' · Pausada por una acción prioritaria' if paused else self._baseline
        if message != current:
            self._show_owned(message)

    def handle_job_event(self, event):
        # Real coordinator events always carry an ID. Do not invent jobs for
        # legacy phase-only notifications or merge unrelated jobs by their label.
        ident, kind = event.get('id'), event.get('kind')
        if ident is not None:
            if kind in ('started', 'resumed'):
                job = self._jobs.setdefault(ident, {'label': event.get('label', 'Tarea de Maximo'), 'started': time.monotonic()})
                job['paused'] = False
                self._active_job = ident
                self._baseline = ''
            elif kind == 'paused':
                if ident in self._jobs:
                    self._jobs[ident]['paused'] = True
                if self._active_job == ident:
                    self._active_job = None
            elif kind in ('finished', 'cancelled'):
                self._jobs.pop(ident, None)
                if self._active_job == ident:
                    self._active_job = None
            self._sync_timer()
        if event.get('label') == 'Actualizar listado de Maximo':
            phases = {'waiting': 'En espera de otra tarea', 'paused': 'Pausada por una acción prioritaria',
                      'started': 'Preparando sesión', 'resumed': 'Reanudando actualización'}
            if kind in phases:
                self.update_progress(phases[kind])
        self._render_progress()
