"""Theme regression matrix for all native MD surface families; no live operations."""
import tests
from pathlib import Path
import sys
from unittest import TestCase
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QApplication,QDialog,QLabel,QPlainTextEdit,QLineEdit,
    QDateTimeEdit,QMessageBox,QPushButton,QCalendarWidget,QToolButton)
from tests import test_filters as fixtures
from tests.theme_surfaces import create_surfaces,close_surfaces
from technician_repair_ui import RepairDialog,RepairProgressDialog,RepairDateTimePopup
from warehouse import WarehouseItem
from failure_catalog import default_selection
from appearance import contrast_ratio
import ui_qt as qt


class ThemeSurfaceTests(TestCase):
    def setUp(self):
        self.fixture=fixtures.FilterTests('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_all_surfaces_follow_six_variants_including_already_open_dialogs(self):
        with self.fixture.qt_window() as (main,_):
            with patch('PySide6.QtCore.QThread.start',side_effect=AssertionError('No jobs in theme tests')):
                surfaces=create_surfaces(main,Path(self.fixture.temp_path)/'reports')
                try:
                    for theme in qt.THEME_PALETTES:
                        for profile in ('normal','comfortable','contrast'):
                            qt.apply_application_theme(QApplication.instance(),theme,profile)
                            QApplication.processEvents()
                            colors=qt.ACTIVE_COLORS
                            for name,widget in surfaces.items():
                                with self.subTest(theme=theme,profile=profile,surface=name):
                                    widget.ensurePolished()
                                    if isinstance(widget,QDialog) and name!='activity':
                                        self.assertEqual(widget.palette().color(QPalette.Window).name(),colors['canvas'])
                                    for control in widget.findChildren(QPlainTextEdit)+widget.findChildren(QLineEdit)+widget.findChildren(QDateTimeEdit):
                                        control.ensurePolished()
                                        if not control.isEnabled():continue
                                        self.assertGreaterEqual(contrast_ratio(control.palette().color(QPalette.Text).name(),control.palette().color(QPalette.Base).name()),4.5)
                            repair=surfaces['repair-close']
                            self.assertEqual(repair.review_panel.palette().color(QPalette.Window).name(),colors['canvas'])
                            self.assertEqual(repair.fault.palette().color(QPalette.WindowText).name(),colors['text'])
                            self.assertEqual(repair.time.palette().color(QPalette.Base).name(),colors['surface'])
                            confirmation=surfaces['message-confirmation']
                            label=confirmation.findChild(QLabel,'qt_msgbox_label');label.ensurePolished()
                            self.assertEqual(label.palette().color(QPalette.WindowText).name(),colors['text'])
                            self.assertEqual(surfaces['repair-progress'].message.palette().color(QPalette.WindowText).name(),colors['text'])
                            self.assertEqual(surfaces['release-notes'].browser.palette().color(QPalette.Base).name(),colors['surface'])
                            calendar=surfaces['calendar'];calendar.ensurePolished()
                            self.assertEqual(calendar.weekdayTextFormat(Qt.Monday).foreground().color().name(),colors['text'])
                            self.assertEqual(calendar.weekdayTextFormat(Qt.Sunday).foreground().color().name(),colors['danger'])
                            self.assertIsNotNone(calendar.findChild(QToolButton,'qt_calendar_prevmonth'))
                            self.assertFalse(calendar.findChild(QToolButton,'qt_calendar_prevmonth').icon().isNull())
                finally:
                    close_surfaces(surfaces,main)
                    qt.apply_application_theme(QApplication.instance(),'light','normal')

    def test_repair_opened_without_ui_qt_module_alias_has_no_light_fallback(self):
        app=QApplication.instance() or QApplication([])
        qt.apply_application_theme(app,'dark')
        try:
            with patch.dict(sys.modules,{'ui_qt':None}),patch('technician_repair_ui.get_fault_description',return_value='Fallo ficticio'):
                repair=RepairDialog(WarehouseItem('DEMO'),default_selection(),autoload=False)
                progress=RepairProgressDialog(repair)
                popup=RepairDateTimePopup(repair.time)
                try:
                    for widget in (repair,progress,popup):
                        widget.ensurePolished()
                        self.assertEqual(widget.styleSheet(),'')
                        self.assertEqual(widget.palette().color(QPalette.Window).name(),qt.ACTIVE_COLORS['canvas'])
                    repair.justification.ensurePolished()
                    self.assertEqual(repair.justification.palette().color(QPalette.Base).name(),qt.ACTIVE_COLORS['surface'])
                finally:
                    popup.deleteLater();progress.deleteLater();repair.deleteLater();app.processEvents()
        finally:qt.apply_application_theme(app,'light')
