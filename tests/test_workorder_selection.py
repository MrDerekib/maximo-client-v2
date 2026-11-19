"""Checkbox selection uses the same rows as Qt keyboard and context actions."""
import tests  # Isolate application data before importing product modules.
from unittest import TestCase
from unittest.mock import Mock, patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QMainWindow, QStyleFactory, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from config import AppConfig
from workorder_selection import WorkorderSelection, prepare_row_context_selection
from warehouse_ui import WarehouseWindowMixin


class SelectionHost(WarehouseWindowMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = AppConfig()
        self.table = QTableWidget(4, 8)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for row in range(4):
            for column in range(8):
                value = f'DEMO-{row}' if column == 1 else 'WAPPR' if column == 7 else 'Dato'
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.selector = WorkorderSelection(self.table, self)
        root = QWidget(); layout = QVBoxLayout(root)
        layout.addWidget(self.selector.bar); layout.addWidget(self.table)
        self.setCentralWidget(root)
        self.resize(950, 400)
        self.selector.set_enabled(True)


class WorkorderSelectionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host = SelectionHost()
        self.host.show()
        self.app.processEvents()

    def tearDown(self):
        self.host.close(); self.host.deleteLater(); self.app.processEvents()

    def checked_ots(self):
        return {self.host.table.item(row, 1).text() for row in range(self.host.table.rowCount())
                if row in self.host.selector.selected_rows()}

    def click_checkbox(self, row, modifiers=Qt.NoModifier):
        table = self.host.table
        gutter=self.host.selector.gutter
        point=QPoint(gutter.width()//2,gutter.sectionViewportPosition(row)+gutter.sectionSize(row)//2)
        QTest.mouseClick(gutter.viewport(),Qt.LeftButton,modifiers,point)
        self.app.processEvents()

    def click_body(self, row, modifiers=Qt.NoModifier):
        table = self.host.table
        rect = table.visualRect(table.model().index(row, 1))
        QTest.mouseClick(table.viewport(), Qt.LeftButton, modifiers, rect.center())
        self.app.processEvents()

    def test_clicking_checkboxes_adds_and_removes_rows_without_clearing_others(self):
        self.click_checkbox(0)
        self.click_checkbox(2)
        self.assertEqual(self.checked_ots(), {'DEMO-0', 'DEMO-2'})
        self.assertEqual({item.ot for item in self.host.warehouse_items()}, self.checked_ots())
        self.assertEqual(self.host.selector.counter.text(), '2 OTs seleccionadas')
        self.assertEqual(self.host.selector.all_checkbox.checkState(), Qt.PartiallyChecked)
        self.click_checkbox(0)
        self.assertEqual(self.checked_ots(), {'DEMO-2'})
        self.host.selector.clear_button.click()
        self.assertEqual(self.checked_ots(), set())
        self.assertFalse(self.host.selector.clear_button.isEnabled())

    def test_ctrl_and_shift_body_selection_updates_checkboxes_and_context_preserves_it(self):
        self.click_body(0)
        self.click_body(2, Qt.ControlModifier)
        self.assertEqual(self.checked_ots(), {'DEMO-0', 'DEMO-2'})
        prepare_row_context_selection(self.host.table, self.host.table.model().index(2, 1))
        self.assertEqual(self.checked_ots(), {'DEMO-0', 'DEMO-2'})
        self.click_body(0)
        self.click_body(2, Qt.ShiftModifier)
        self.assertEqual(self.checked_ots(), {'DEMO-0', 'DEMO-1', 'DEMO-2'})

    def test_header_selects_only_visible_rows_and_partial_click_selects_all(self):
        self.host.table.setRowHidden(1, True)
        self.host.selector.refresh()
        self.click_checkbox(0)
        self.assertEqual(self.host.selector.all_checkbox.checkState(), Qt.PartiallyChecked)
        self.host.selector.all_checkbox.click()
        self.assertEqual(self.checked_ots(), {'DEMO-0', 'DEMO-2', 'DEMO-3'})
        self.assertEqual(self.host.selector.all_checkbox.checkState(), Qt.Checked)
        self.assertEqual(self.host.selector.counter.text(), '3 OTs seleccionadas')
        self.host.selector.all_checkbox.click()
        self.assertFalse(self.checked_ots())

    def test_sorting_keeps_ot_identity_in_checkboxes_and_batch(self):
        self.click_checkbox(0); self.click_checkbox(2)
        self.host.table.setSortingEnabled(True)
        self.host.table.sortItems(1, Qt.DescendingOrder)
        self.app.processEvents()
        self.assertEqual(self.checked_ots(), {'DEMO-0', 'DEMO-2'})
        self.assertEqual({item.ot for item in self.host.warehouse_items()}, self.checked_ots())

    def test_model_rebuild_clears_selection_and_new_rows_start_unchecked(self):
        self.host.selector.all_checkbox.click()
        self.host.table.setRowCount(0)
        self.host.table.setRowCount(1)
        for column in range(8):
            self.host.table.setItem(0, column, QTableWidgetItem('NEW'))
        self.app.processEvents()
        self.assertFalse(self.checked_ots())
        self.assertEqual(self.host.selector.counter.text(), '0 OTs seleccionadas')
        self.assertEqual(self.host.selector.all_checkbox.checkState(), Qt.Unchecked)

    def test_hidden_selected_rows_are_pruned_and_disabling_removes_selector(self):
        self.host.selector.all_checkbox.click()
        self.host.table.setRowHidden(0, True)
        self.host.selector.refresh()
        self.assertNotIn('DEMO-0', self.checked_ots())
        self.host.selector.set_enabled(False)
        self.assertTrue(self.host.selector.bar.isHidden())
        self.assertTrue(self.host.selector.all_checkbox.isHidden())
        self.assertEqual(self.host.table.item(1, 0).data(Qt.CheckStateRole), None)
        self.assertFalse(self.host.table.selectionModel().selectedRows())
        self.assertIs(self.host.table.itemDelegate(), self.host.selector.original_delegate)

    def test_empty_table_has_no_select_all_action(self):
        self.host.table.setRowCount(0)
        self.app.processEvents()
        self.assertFalse(self.host.selector.all_checkbox.isEnabled())
        self.assertEqual(self.host.selector.counter.text(), '0 OTs seleccionadas')

    def test_shift_checkbox_selection_skips_hidden_rows(self):
        self.host.table.setRowHidden(1, True)
        self.host.selector.refresh()
        self.click_checkbox(0)
        self.click_checkbox(3, Qt.ShiftModifier)
        self.assertEqual(self.checked_ots(), {'DEMO-0', 'DEMO-2', 'DEMO-3'})

    def test_model_reset_between_press_and_release_does_not_select_a_replacement_ot(self):
        table = self.host.table
        gutter=self.host.selector.gutter
        point=QPoint(2,gutter.sectionViewportPosition(0)+gutter.sectionSize(0)//2)
        QTest.mousePress(gutter.viewport(), Qt.LeftButton, Qt.NoModifier, point)
        table.setRowCount(0); table.setRowCount(1)
        for column in range(8):
            table.setItem(0, column, QTableWidgetItem('NEW'))
        QTest.mouseRelease(gutter.viewport(), Qt.LeftButton, Qt.NoModifier, point)
        self.app.processEvents()
        self.assertFalse(table.selectionModel().selectedRows())
        self.assertFalse(self.checked_ots())

    def test_priority_filter_toggle_clears_selection_without_warehouse_enabled(self):
        from tests.test_ui_app_updates import MaximoDesktopWindow
        self.host._workorder_selector = self.host.selector
        self.host._apply_priority_filter = Mock()
        self.host._update_list_summary = Mock()
        self.click_checkbox(0); self.click_checkbox(2)
        MaximoDesktopWindow._toggle_priority_filter(self.host, True)
        self.assertFalse(self.checked_ots())
        self.host._apply_priority_filter.assert_called_once()

    def test_warehouse_actions_can_toggle_without_changing_general_selection(self):
        from PySide6.QtWidgets import QMenu
        self.click_checkbox(0); self.click_checkbox(2)
        for enabled in (True, False, True, False):
            self.host.cfg.warehouse_enabled = enabled
            menu = QMenu()
            self.host.add_warehouse_actions(menu)
            self.assertEqual(bool(menu.actions()), enabled)
            self.assertTrue(self.host.selector.enabled)
            self.assertFalse(self.host.selector.bar.isHidden())
            self.assertEqual(self.checked_ots(), {'DEMO-0', 'DEMO-2'})

    def test_selected_cells_have_a_solid_background_with_windows11_and_fusion(self):
        old_style = self.app.style().objectName()
        old_sheet = self.app.styleSheet()
        try:
            for style in ('windows11', 'Fusion'):
                if style.lower() not in {name.lower() for name in QStyleFactory.keys()}:
                    continue
                with self.subTest(style=style):
                    self.app.setStyle(style)
                    self.app.setStyleSheet('QTableWidget { selection-background-color: #dbeafe; '
                                          'selection-color: #172033; }')
                    self.host.selector.clear_selection()
                    self.host.table.item(0, 4).setText('')
                    self.click_checkbox(0)
                    self.app.processEvents()
                    image = self.host.table.viewport().grab().toImage()
                    rect = self.host.table.visualRect(self.host.table.model().index(0, 4))
                    for point in (rect.topLeft()+QPoint(2, 2), rect.center(), rect.bottomRight()-QPoint(2, 2)):
                        self.assertEqual(image.pixelColor(point).name(), '#dbeafe')
                    self.assertEqual(self.checked_ots(), {'DEMO-0'})
        finally:
            self.app.setStyle(old_style or 'Fusion')
            self.app.setStyleSheet(old_sheet)

    def test_entire_gutter_cell_is_clickable_not_only_the_tick(self):
        gutter=self.host.selector.gutter
        y=gutter.sectionViewportPosition(1)+gutter.sectionSize(1)//2
        for x in (2,gutter.width()-2):
            QTest.mouseClick(gutter.viewport(),Qt.LeftButton,Qt.NoModifier,QPoint(x,y))
            self.app.processEvents()
            self.assertEqual(self.checked_ots(),{'DEMO-1'} if x==2 else set())
        self.assertEqual(gutter.width(),44)
        self.assertIsNone(self.host.table.item(1,0).data(Qt.CheckStateRole))

    def test_plain_click_focus_change_and_double_click_preserve_marked_batch(self):
        self.click_checkbox(0);self.click_checkbox(2)
        self.click_body(1)
        self.assertEqual(self.checked_ots(),{'DEMO-0','DEMO-2'})
        self.assertEqual({i.ot for i in self.host.warehouse_items()},self.checked_ots())
        self.host.selector.clear_button.setFocus();self.app.processEvents()
        self.assertEqual(self.checked_ots(),{'DEMO-0','DEMO-2'})
        opened=Mock();self.host.table.cellDoubleClicked.connect(opened)
        rect=self.host.table.visualRect(self.host.table.model().index(3,1))
        self.click_body(3)  # Qt double-click follows the first press/release on this row.
        QTest.mouseDClick(self.host.table.viewport(),Qt.LeftButton,Qt.NoModifier,rect.center())
        self.app.processEvents();opened.assert_called_once_with(3,1)
        self.assertEqual(self.checked_ots(),{'DEMO-0','DEMO-2'})

    def test_context_on_unmarked_row_is_individual_without_destroying_batch(self):
        self.click_checkbox(0);self.click_checkbox(2)
        prepare_row_context_selection(self.host.table,self.host.table.model().index(1,1))
        self.assertEqual([i.ot for i in self.host.warehouse_items()],['DEMO-1'])
        self.assertEqual(self.checked_ots(),{'DEMO-0','DEMO-2'})
        self.host.selector.clear_context()
        self.assertEqual({i.ot for i in self.host.warehouse_items()},self.checked_ots())
        prepare_row_context_selection(self.host.table,self.host.table.model().index(2,1))
        self.assertEqual({i.ot for i in self.host.warehouse_items()},self.checked_ots())

    def test_keyboard_space_ctrl_a_and_navigation_keep_marks(self):
        self.click_body(1);self.assertFalse(self.checked_ots())
        QTest.keyClick(self.host.table,Qt.Key_Space)
        self.assertEqual(self.checked_ots(),{'DEMO-1'})
        QTest.keyClick(self.host.table,Qt.Key_Down)
        self.assertEqual(self.checked_ots(),{'DEMO-1'})
        QTest.keyClick(self.host.table,Qt.Key_A,Qt.ControlModifier)
        self.assertEqual(self.checked_ots(),{f'DEMO-{i}' for i in range(4)})

    def test_large_batch_does_not_write_cell_data_and_survives_sorting(self):
        from PySide6.QtTest import QSignalSpy
        table=QTableWidget(4500,2)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for row in range(table.rowCount()):
            table.setItem(row,0,QTableWidgetItem('Activo'))
            table.setItem(row,1,QTableWidgetItem(f'OT-{row:05}'))
        selector=WorkorderSelection(table);selector.set_enabled(True)
        data_changes=QSignalSpy(table.model().dataChanged)
        try:
            selector.all_checkbox.click()
            self.assertEqual(len(selector.selected_rows()),4500)
            self.assertEqual(data_changes.count(),0)
            table.setSortingEnabled(True);table.sortItems(1,Qt.DescendingOrder);self.app.processEvents()
            self.assertEqual(len(selector.selected_rows()),4500)
            self.assertEqual(data_changes.count(),0)
            selector.clear_selection();self.assertFalse(selector.selected_rows())
        finally:table.close();table.deleteLater();self.app.processEvents()

    def test_delayed_refresh_is_safe_after_table_destruction(self):
        from shiboken6 import delete
        from PySide6.QtCore import QEvent
        table=QTableWidget(1,2)
        selector=WorkorderSelection(table,self.host)
        selector.set_enabled(True)
        delete(table)
        selector._queue_refresh();selector.refresh()
        self.assertEqual(selector.selected_rows(),[])
        self.assertFalse(selector.eventFilter(self.host,QEvent(QEvent.Show)))

    def test_escape_and_click_outside_clear_but_focus_alone_does_not(self):
        from PySide6.QtWidgets import QLabel
        outside=QLabel('Zona fuera de la tabla',self.host.centralWidget())
        self.host.centralWidget().layout().insertWidget(0,outside)
        self.app.processEvents()
        self.click_checkbox(0);self.click_checkbox(2)
        self.host.selector.clear_button.setFocus();self.app.processEvents()
        self.assertEqual(self.checked_ots(),{'DEMO-0','DEMO-2'})
        QTest.keyClick(self.host.table,Qt.Key_Escape)
        self.assertFalse(self.checked_ots());self.assertFalse(self.host.table.selectionModel().selectedRows())
        self.click_checkbox(0);QTest.mouseClick(outside,Qt.LeftButton)
        self.assertFalse(self.checked_ots())

    def test_outside_operation_button_receives_batch_and_menu_escape_keeps_it(self):
        from PySide6.QtWidgets import QPushButton,QMenu
        button=QPushButton('Operar sobre el lote',self.host.centralWidget())
        self.host.centralWidget().layout().insertWidget(0,button);self.app.processEvents()
        received=[];button.clicked.connect(lambda:received.append(self.checked_ots()))
        self.click_checkbox(0);self.click_checkbox(2)
        QTest.mouseClick(button,Qt.LeftButton)
        self.assertEqual(received,[{'DEMO-0','DEMO-2'}])
        menu=QMenu(self.host);menu.addAction('Acción de prueba');menu.popup(button.mapToGlobal(QPoint(0,0)))
        self.app.processEvents();QTest.keyClick(menu,Qt.Key_Escape)
        self.assertEqual(self.checked_ots(),{'DEMO-0','DEMO-2'})
        menu.deleteLater()

    def test_click_empty_table_area_clears_marks(self):
        self.click_checkbox(0);self.click_checkbox(2)
        QTest.mouseClick(self.host.table.viewport(),Qt.LeftButton,Qt.NoModifier,self.host.table.viewport().rect().bottomRight()-QPoint(3,3))
        self.assertFalse(self.checked_ots())
