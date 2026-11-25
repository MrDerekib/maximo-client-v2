import tests
from unittest import TestCase
from unittest.mock import patch
from config import AppConfig
from tests import test_filters as fixtures


class SidebarTests(TestCase):
    def setUp(self):
        self.fixture=fixtures.FilterTests('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_main_header_hides_and_recovers_sidebar_without_query_or_selection_loss(self):
        with self.fixture.qt_window() as (window,qt):
            window.show();qt.QApplication.processEvents()
            window.table.selectRow(1)
            selected=[index.row() for index in window.table.selectionModel().selectedRows()]
            cells=[window.table.item(row,1) for row in range(window.table.rowCount())]
            before=window.table.viewport().width()
            toggle=window.sidebar_toggle
            with patch.object(qt,'save_config') as save,patch.object(qt,'fetch_data') as fetch:
                toggle.click();qt.QApplication.processEvents()
                self.assertTrue(window.sidebar.isHidden());self.assertTrue(window.cfg.sidebar_collapsed)
                self.assertTrue(toggle.isVisible());self.assertFalse(toggle.icon().isNull())
                self.assertEqual(toggle.accessibleName(),'Mostrar barra lateral')
                self.assertGreater(window.table.viewport().width(),before)
                self.assertEqual([window.table.item(row,1) for row in range(window.table.rowCount())],cells)
                self.assertEqual([index.row() for index in window.table.selectionModel().selectedRows()],selected)
                fetch.assert_not_called();save.assert_called_once()
                window.settings_nav_button.click()
                qt.QApplication.processEvents()
                self.assertEqual(window.pages.currentIndex(),1)
                self.assertFalse(window.settings_nav_button.icon().isNull())
                toggle_settings=window.sidebar_toggle
                self.assertTrue(toggle_settings.isVisible())
                window.user_edit.setText('escritura-pendiente')
                self.assertEqual(window.sidebar_visibility_action.text(), 'Mostrar barra lateral')
                window.sidebar_visibility_action.trigger()
                qt.QApplication.processEvents()
                self.assertFalse(window.sidebar.isHidden());self.assertFalse(window.cfg.sidebar_collapsed)
                self.assertEqual(window.user_edit.text(),'escritura-pendiente')
                self.assertEqual(window.cfg.username,'')  # Hiding the sidebar never applies pending settings.
                self.assertEqual(save.call_count,2)
                fetch.assert_not_called()
                window.user_edit.clear()
                list_action = next(action for action in window.view_menu_button.menu().actions()
                                   if action.text() == 'Listado')
                list_action.trigger()
                self.assertEqual(window.pages.currentIndex(), 0)

    def test_sidebar_preference_is_restored_with_a_visible_control(self):
        with self.fixture.qt_window(AppConfig(sidebar_collapsed=True)) as (window,qt):
            window.show();qt.QApplication.processEvents()
            self.assertTrue(window.sidebar.isHidden())
            toggle=window.sidebar_toggle
            self.assertTrue(toggle.isVisible());self.assertFalse(toggle.icon().isNull())
        self.assertFalse(AppConfig(sidebar_collapsed='yes').sidebar_collapsed)

    def test_export_in_sidebar_and_selection_in_filter_card_without_height_jump(self):
        with self.fixture.qt_window() as (window,qt):
            window.show();qt.QApplication.processEvents()
            selector=window._workorder_selector
            self.assertTrue(window.sidebar.isAncestorOf(window.export_button))
            self.assertFalse(hasattr(window,'nav_buttons'))
            self.assertTrue(window.search_card.isAncestorOf(selector.clear_button))
            self.assertFalse(selector.clear_button.isVisible())
            before=window.search_card.height()
            window.table.selectRow(1);qt.QApplication.processEvents()
            self.assertTrue(selector.clear_button.isVisible())
            self.assertEqual(window.search_card.height(),before)
            self.assertIn('1 OT seleccionada',selector.counter.text())
            selector.clear_button.click();qt.QApplication.processEvents()
            self.assertFalse(window.table.selectionModel().selectedRows())
            self.assertFalse(selector.clear_button.isVisible())
            self.assertEqual(window.search_card.height(),before)
            self.assertEqual(window.export_action.text(),'Exportar a Excel')
            window._set_sidebar_visible(False)
            self.assertTrue(window.file_menu_button.isVisible())
            self.assertIn(window.export_action, window.file_menu_button.menu().actions())
            self.assertIn(window.fault_run_action, window.maximo_menu_button.menu().actions())
            self.assertIn(window.fault_cancel_action, window.maximo_menu_button.menu().actions())
            self.assertFalse(window.fault_cancel_action.isEnabled())
            self.assertFalse(hasattr(window, 'navigation_location'))
            sync = next(action for action in window.maximo_menu_button.menu().actions()
                        if action.text() == 'Actualizar Maximo')
            with patch.object(window, 'update_now') as update:
                sync.trigger()
            update.assert_called_once_with()

    def test_sidebar_drag_preserves_rows_marks_and_pending_settings(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        with self.fixture.qt_window() as (window, qt):
            window.resize(1500, 980); window.show(); qt.QApplication.processEvents()
            selector=window._workorder_selector
            selector._toggle_row(window.table.model().index(1,0), Qt.NoModifier)
            marked=selector.selected_rows()
            cells=[window.table.item(row,1) for row in range(window.table.rowCount())]
            window.user_edit.setText('sin-guardar')
            width=window.sidebar.width()
            handle=window.sidebar_splitter.handle(1)
            middle=handle.rect().center()
            target=middle+QPoint(80,0)
            with patch.object(qt,'save_config') as save, patch.object(qt,'fetch_data') as fetch:
                QTest.mousePress(handle,Qt.LeftButton,pos=middle)
                QTest.mouseMove(handle,target,20)
                QTest.mouseRelease(handle,Qt.LeftButton,pos=target)
                qt.QApplication.processEvents()
                self.assertGreater(window.sidebar.width(),width+40)
                self.assertEqual(window.cfg.sidebar_width,window.sidebar.width())
                self.assertGreaterEqual(save.call_count,1)
                fetch.assert_not_called()
                self.assertEqual(selector.selected_rows(),marked)
                self.assertEqual([window.table.item(row,1) for row in range(window.table.rowCount())],cells)
                self.assertEqual(window.user_edit.text(),'sin-guardar')
                self.assertEqual(window.cfg.username,'')
                saved=window.cfg.sidebar_width
                window.toggle_sidebar();qt.QApplication.processEvents()
                window.toggle_sidebar();qt.QApplication.processEvents()
                self.assertEqual(window.sidebar.width(),saved)
                self.assertTrue(window.settings_dirty())

    def test_sidebar_width_restores_and_migrates_safely(self):
        self.assertEqual(AppConfig().sidebar_width,226)
        for value,expected in ((None,226),('bad',226),(0,210),(9999,420),('310',310)):
            self.assertEqual(AppConfig(sidebar_width=value).sidebar_width,expected)
        for collapsed in (False,True):
            with self.fixture.qt_window(AppConfig(sidebar_width=330,sidebar_collapsed=collapsed)) as (window,qt):
                window.resize(1500,980);window.show();qt.QApplication.processEvents()
                if collapsed:
                    with patch.object(qt,'save_config'):window.toggle_sidebar()
                    qt.QApplication.processEvents()
                self.assertAlmostEqual(window.sidebar.width(),330,delta=2)
