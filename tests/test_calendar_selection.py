import tests
from unittest import TestCase
from PySide6.QtCore import QDate,QDateTime,QTime
from PySide6.QtWidgets import QApplication,QAbstractItemView
from technician_repair_ui import RepairTimeEdit
from appearance import THEME_PALETTES
import ui_qt as qt

class CalendarSelectionTests(TestCase):
    def test_selected_day_remains_accented_after_focus_moves_to_hour_in_every_theme(self):
        app=QApplication.instance() or QApplication([])
        editor=RepairTimeEdit(QDateTime(QDate(2026,11,19),QTime(7,15)))
        editor.setCalendarPopup(True)
        editor.show_date_time_popup();popup=editor._date_time_popup
        try:
            popup.calendar.setSelectedDate(QDate(2026,11,18))
            for theme in THEME_PALETTES:
                with self.subTest(theme=theme):
                    qt.apply_application_theme(app,theme)
                    popup.hour.setFocus();popup.adjustSize();app.processEvents()
                    view=popup.calendar.findChild(QAbstractItemView,'qt_calendar_calendarview')
                    rect=view.visualRect(view.selectionModel().selectedIndexes()[0])
                    self.assertTrue(rect.isValid())
                    image=view.viewport().grab().toImage()
                    self.assertEqual(image.pixelColor(rect.left()+4,rect.top()+4).name(),qt.ACTIVE_COLORS['accent'])
        finally:
            popup.reject();popup.deleteLater();editor.deleteLater()
            qt.apply_application_theme(app,'light')
