import tests  # Isolate application data before importing product modules.
from unittest import TestCase
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication,QLabel
from ui_qt import show_activity_dialog
from priority_notices import PriorityNotices
from task_priorities import HIGH,AUTOMATIC


class NoticeTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_waiting_notice_is_visible_and_closes_when_action_starts(self):
        notices=PriorityNotices(lambda text:show_activity_dialog(text),Mock())
        event={'kind':'waiting','id':'1','priority':HIGH,'embedded':False,
               'message':'Terminando conciliación · OT 123. Después comenzará Confirmar recepción.'}
        try:
            notices.event_received.emit(event);self.app.processEvents()
            dialog=notices.dialogs['1']
            self.assertTrue(dialog.isVisible())
            self.assertIn('123',dialog.findChild(QLabel,'activityMessage').text())
            notices.event_received.emit({**event,'kind':'started'});self.app.processEvents()
            self.assertFalse(dialog.isVisible())
            self.assertEqual(notices.dialogs,{})
        finally:notices.close()

    def test_background_or_embedded_wait_does_not_open_another_popup(self):
        factory=Mock();notices=PriorityNotices(factory,Mock())
        for priority,embedded in ((AUTOMATIC,False),(HIGH,True)):
            notices.handle({'kind':'waiting','id':'1','priority':priority,'embedded':embedded,'message':'Espera'})
        factory.assert_not_called();notices.close()
