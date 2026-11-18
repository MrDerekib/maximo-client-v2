"""Headers and the selector must stay inside the rounded outer table frame."""
import tests
from unittest import TestCase
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication
from tests import test_filters as fixtures
import ui_qt as qt


class RoundedTableTests(TestCase):
    def setUp(self):
        self.fixture=fixtures.FilterTests('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_headers_are_clipped_and_outer_border_is_visible_on_both_left_corners(self):
        with self.fixture.qt_window() as (window,_):
            window.resize(1400,850);window.show()
            for theme in ('light','gruvbox_dark'):
                qt.apply_application_theme(QApplication.instance(),theme);QApplication.processEvents()
                table=window.table;frame=window.table_frame
                for size in ((1400,850),(1100,700)):
                    window.resize(*size);QApplication.processEvents()
                    rect=table.rect();mask=table.mask()
                    for point in (rect.topLeft(),rect.topRight(),rect.bottomLeft(),rect.bottomRight()):
                        self.assertFalse(mask.contains(point))
                    self.assertTrue(mask.contains(rect.center()))
                    self.assertTrue(mask.contains(QPoint(0,rect.height()//2)))
                    image=frame.grab().toImage();colors=qt.ACTIVE_COLORS
                    self.assertEqual(image.pixelColor(0,frame.height()//2).name(),colors['border'])
                    self.assertEqual(image.pixelColor(10,0).name(),colors['border'])
                    self.assertEqual(image.pixelColor(10,frame.height()-1).name(),colors['border'])
                    self.assertEqual(table.columnCount(),len(window.columns))
            table.setRowCount(0);QApplication.processEvents()
            self.assertFalse(table.mask().contains(table.rect().topLeft()))

    def test_technician_entry_progress_and_sat_tables_clip_corners_when_resized(self):
        from unittest.mock import patch
        from technician_repair_ui import RepairDialog,RepairProgressDialog
        from technician_sat_ui import TechnicianSatDialog
        from failure_catalog import default_selection
        from warehouse import WarehouseItem
        with self.fixture.qt_window() as (main,_):
            with patch('technician_repair_ui.get_fault_description',return_value='Avería ficticia'):
                repair=RepairDialog(WarehouseItem('DEMO'),default_selection(),main,autoload=False)
            progress=RepairProgressDialog(repair)
            sat=TechnicianSatDialog([WarehouseItem('DEMO')],lambda _:None,main,
                selection=default_selection(),report_folder=self.fixture.temp_path,autoload=False)
            try:
                repair.add_entry('Prueba','Detalles ficticios')
                for theme in ('light','gruvbox_dark'):
                    qt.apply_application_theme(QApplication.instance(),theme)
                    for dialog,frame in ((repair,repair.entries_frame),(progress,progress.table_frame),(sat,sat.table_frame)):
                        with self.subTest(theme=theme,dialog=type(dialog).__name__):
                            dialog.show()
                            for width in (1100,850):
                                dialog.resize(width,900);QApplication.processEvents()
                                table=frame.table;rect=table.rect()
                                for point in (rect.topLeft(),rect.topRight(),rect.bottomLeft(),rect.bottomRight()):
                                    self.assertFalse(table.mask().contains(point))
                                self.assertTrue(table.mask().contains(rect.center()))
                                image=frame.grab().toImage()
                                self.assertEqual(image.pixelColor(0,frame.height()//2).name(),qt.ACTIVE_COLORS['border'])
                                self.assertEqual(image.pixelColor(10,0).name(),qt.ACTIVE_COLORS['border'])
                                self.assertEqual(image.pixelColor(10,frame.height()-1).name(),qt.ACTIVE_COLORS['border'])
                            dialog.hide()
            finally:
                for dialog in (sat,progress,repair):dialog.hide();dialog.deleteLater()
                QApplication.processEvents()
