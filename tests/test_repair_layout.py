"""Offline geometry regression: no Maximo sessions or state changes."""
import tests
from unittest import TestCase
from unittest.mock import patch
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont,QFontDatabase
from tests import test_filters as fixtures
from technician_repair_ui import RepairDialog
from warehouse import WarehouseItem
from failure_catalog import default_selection
import ui_qt as qt

class RepairLayoutTests(TestCase):
    def setUp(self):
        self.fixture=fixtures.FilterTests('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_full_form_fits_desktop_and_action_change_does_not_resize(self):
        with self.fixture.qt_window() as (main,_):
            for name in ('segoeui.ttf','seguisb.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
            app=QApplication.instance();original_font=app.font()
            self.addCleanup(lambda:app.setFont(original_font))
            app.setFont(QFont('Segoe UI',9))
            for theme in ('light','dark'):
                qt.apply_application_theme(QApplication.instance(),theme,'normal')
                with patch('technician_repair_ui.get_fault_description',return_value='Avería de prueba'):
                    dialog=RepairDialog(WarehouseItem('DEMO'),default_selection(),main,autoload=False)
                try:
                    dialog.fit_initial_size(QRect(0,0,1920,1040));dialog.show()
                    QApplication.processEvents()
                    size=dialog.size()
                    for action in ('discard','close','discard'):
                        dialog.action.setCurrentIndex(dialog.action.findData(action))
                        QApplication.processEvents()
                        self.assertEqual(dialog.size(),size)
                        self.assertEqual(dialog.review_scroll.verticalScrollBar().maximum(),0)
                        self.assertTrue(dialog.confirm.isVisible())
                    dialog.fit_initial_size(QRect(0,0,1280,720))
                    QApplication.processEvents()
                    self.assertLessEqual(dialog.height(),672)
                    self.assertGreater(dialog.review_scroll.verticalScrollBar().maximum(),0)
                finally:dialog.close();dialog.deleteLater()
