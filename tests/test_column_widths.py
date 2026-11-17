"""Column preferences are changed by user gestures, not viewport adaptations."""
import tests
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from config import AppConfig
from tests import test_filters as fixtures


class ColumnWidthTests(TestCase):
    def setUp(self):
        self.f=fixtures.FilterTests('runTest');self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def drag(self,w,index=1,delta=35):
        h=w.table.horizontalHeader();v=h.viewport()
        x=h.sectionViewportPosition(index)+h.sectionSize(index)-1
        y=v.height()//2
        QTest.mousePress(v,Qt.LeftButton,pos=QPoint(x,y))
        QTest.mouseMove(v,QPoint(x+delta,y),delay=20)
        QTest.mouseRelease(v,Qt.LeftButton,pos=QPoint(x+delta,y))

    def test_initial_and_programmatic_layout_changes_never_save_preferences(self):
        with self.f.qt_window() as (w,qt):
            w.show();qt.QApplication.processEvents()
            preferred=list(w._column_widths)
            self.assertFalse(w._column_width_save_timer.isActive())
            with patch.object(qt,'save_config') as save:
                w.table.horizontalHeader().resizeSection(1,190)
                w.resize(1300,800);qt.QApplication.processEvents()
                w._fit_columns_to_viewport()
                QTest.qWait(450)
                self.assertEqual(w._column_widths,preferred)
                self.assertFalse(w._column_widths_dirty)
                save.assert_not_called()

    def test_drag_saves_once_after_release_and_ignores_later_auto_fit(self):
        with self.f.qt_window() as (w,qt):
            w.show();qt.QApplication.processEvents()
            with patch.object(qt,'save_config') as save:
                self.drag(w)
                self.assertTrue(w._column_widths_dirty)
                self.assertTrue(w._column_width_save_timer.isActive())
                preferred=list(w._column_widths)
                w.resize(1100,800);w._fit_columns_to_viewport()
                QTest.qWait(450)
                save.assert_called_once()
                self.assertEqual(w.cfg.table_column_widths,{str(i):int(v) for i,v in enumerate(preferred)})
                self.assertFalse(w._column_widths_dirty)
                w._save_column_widths()
                save.assert_called_once()

    def test_close_flushes_pending_drag_in_one_config_write(self):
        with self.f.qt_window() as (w,qt):
            w.show();qt.QApplication.processEvents()
            with patch.object(qt,'save_config') as save:
                self.drag(w)
                preferred=list(w._column_widths)
                w._save_window_state()
                self.assertFalse(w._column_width_save_timer.isActive())
                self.assertEqual(w.cfg.table_column_widths,{str(i):int(v) for i,v in enumerate(preferred)})
                QTest.qWait(450)
                save.assert_called_once()

    def test_closing_after_auto_fit_preserves_saved_user_preferences(self):
        cfg=AppConfig(table_column_widths={str(i):v for i,v in enumerate([180,110,340,145,135,140,180,130,105,140,280])},table_layout_initialized=True)
        original=deepcopy(cfg.table_column_widths)
        with self.f.qt_window(cfg) as (w,qt):
            w.show();qt.QApplication.processEvents()
            w.resize(1000,740);w._fit_columns_to_viewport()
            with patch.object(qt,'save_config') as save:
                w._save_window_state()
            save.assert_called_once()
            self.assertEqual(w.cfg.table_column_widths,original)

    def test_unchanged_pending_preference_does_not_write_again(self):
        with self.f.qt_window() as (w,qt):
            w.cfg.table_column_widths={str(i):int(v) for i,v in enumerate(w._column_widths)}
            w.cfg.table_layout_initialized=True
            w._column_widths_dirty=True
            with patch.object(qt,'save_config') as save:w._save_column_widths()
            save.assert_not_called()
            self.assertFalse(w._column_widths_dirty)

    def test_collapsing_and_resizing_sidebar_fit_columns_without_overwriting_preferences(self):
        with self.f.qt_window() as (w,qt):
            w.show();qt.QApplication.processEvents()
            self.drag(w);w._column_width_save_timer.stop();w._save_column_widths()
            preferred=list(w._column_widths)
            saved=deepcopy(w.cfg.table_column_widths)
            header=w.table.horizontalHeader()
            before=[header.sectionSize(i) for i in w._visible_table_columns()]
            with patch.object(qt,'save_config') as save:
                w.toggle_sidebar();qt.QApplication.processEvents();w._fit_columns_to_viewport()
                expanded=[header.sectionSize(i) for i in w._visible_table_columns()]
                self.assertNotEqual(before,expanded)
                w.toggle_sidebar();qt.QApplication.processEvents();w._fit_columns_to_viewport()
                total=w.sidebar_splitter.width()
                w.sidebar_splitter.setSizes([300,max(600,total-300)])
                qt.QApplication.processEvents();w._sidebar_resized(300,1)
                self.assertEqual(w._column_widths,preferred)
                self.assertEqual(w.cfg.table_column_widths,saved)
                self.assertFalse(w._column_widths_dirty)
                self.assertFalse(w._column_width_save_timer.isActive())
                count=save.call_count
                QTest.qWait(450)
                self.assertEqual(save.call_count,count)
