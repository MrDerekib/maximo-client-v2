"""GUI-side priority notices, prepared independently of MD's existing job execution."""
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QLabel
from task_priorities import MANUAL


class PriorityNotices(QObject):
    event_received = Signal(object)

    def __init__(self, create_notice, status_message, parent=None):
        super().__init__(parent)
        self.create_notice = create_notice
        self.status_message = status_message
        self.dialogs = {}
        self.closed = False
        self.event_received.connect(self.handle)

    @Slot(object)
    def handle(self, event):
        if self.closed:
            return
        kind, ident = event['kind'], event['id']
        if kind == 'waiting' and event['priority'] <= MANUAL and not event['embedded']:
            dialog = self.dialogs.get(ident)
            if dialog is None:
                self.dialogs[ident] = self.create_notice(event['message'])
            else:
                label = dialog.findChild(QLabel,'activityMessage')
                if label is not None:
                    label.setText(event['message'])
                    dialog.adjustSize()
        elif kind in ('started','resumed','finished','cancelled'):
            dialog = self.dialogs.pop(ident,None)
            if dialog is not None:
                dialog.close()
        if kind in ('paused','resumed') or event['priority'] <= MANUAL:
            self.status_message(event['message'])

    def close(self):
        self.closed = True
        for dialog in self.dialogs.values():
            dialog.close()
        self.dialogs.clear()
