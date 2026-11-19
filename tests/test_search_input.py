"""Offline clipboard tests; the real system clipboard is never changed."""
import tests
import sqlite3
from contextlib import closing
from unittest import TestCase
from unittest.mock import Mock, patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication
from search_input import SearchLineEdit, normalize_pasted_search
from tests import test_filters as fixtures
import db


class SearchPasteTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_mail_column_and_excel_cells_become_distinct_alternatives(self):
        raw='\u00a0\r\n4161394\r\n\r\n4336088\t4366707\r4351190\n4355783\n4161394\n'
        self.assertEqual(normalize_pasted_search(raw),'4161394, 4336088, 4366707, 4351190, 4355783')
        self.assertEqual(normalize_pasted_search('AB 456\nCD\u00a0 789\nAB 456'),'AB 456, CD 789')
        self.assertEqual(normalize_pasted_search('AB 456, cd 789, CD 789'),'AB 456, cd 789')

    def test_keyboard_paste_replaces_selection_and_emits_once_without_enter(self):
        w=SearchLineEdit();w.show();self.addCleanup(w.deleteLater)
        w.setText('previous search');w.selectAll()
        applied=QSignalSpy(w.pasted)
        clipboard=Mock();clipboard.text.return_value='12345\n67890'
        with patch('search_input.QApplication.clipboard',return_value=clipboard):
            QTest.keyClick(w,Qt.Key_V,Qt.ControlModifier)
        self.assertEqual(w.text(),'12345, 67890');self.assertEqual(applied.count(),1)
        w.undo();self.assertEqual(w.text(),'previous search')

    def test_context_menu_paste_uses_same_normalization_and_applies_once(self):
        w=SearchLineEdit();self.addCleanup(w.deleteLater)
        clipboard=Mock();clipboard.text.return_value='AB 456\nCD 789'
        applied=QSignalSpy(w.pasted)
        with patch('search_input.QApplication.clipboard',return_value=clipboard):
            menu=w.createStandardContextMenu()
            try:
                action=next(a for a in menu.actions() if a.objectName()=='edit-paste')
                action.setEnabled(True);action.trigger()
            finally:menu.deleteLater()
        self.assertEqual(w.text(),'AB 456, CD 789');self.assertEqual(applied.count(),1)

    def test_empty_clipboard_does_not_clear_search_or_select_everything(self):
        w=SearchLineEdit();self.addCleanup(w.deleteLater)
        w.setText('keep');w.selectAll();applied=QSignalSpy(w.pasted)
        clipboard=Mock();clipboard.text.return_value=' \r\n\t\u00a0'
        with patch('search_input.QApplication.clipboard',return_value=clipboard):w.paste()
        self.assertEqual(w.text(),'keep');self.assertEqual(applied.count(),0)

    def test_partial_serial_search_semantics_are_unchanged_for_each_pasted_row(self):
        f=fixtures.FilterTests('runTest');f.setUp();self.addCleanup(f.doCleanups)
        with closing(sqlite3.connect(f.path)) as conn:
            conn.executemany('INSERT INTO maximo (OT,Nº_de_serie) VALUES (?,?)',[
                ('10001','ABC123456'),('10002','CD123789'),('10003','AB123999')])
            conn.commit()
        text=normalize_pasted_search('AB 456\nCD 789')
        self.assertEqual({row[0] for row in db.fetch_data(text,'Nº_de_serie','Todos')},{'10001','10002'})

    def test_main_search_applies_pasted_column_without_an_extra_action(self):
        f=fixtures.FilterTests('runTest');f.setUp();self.addCleanup(f.doCleanups)
        with f.qt_window() as (w,qt):
            w.search_by_combo.setCurrentIndex(w.search_by_combo.findData('OT'))
            clipboard=Mock();clipboard.text.return_value='1\r\n\r\n3\n1'
            with patch('search_input.QApplication.clipboard',return_value=clipboard), \
                 patch.object(qt,'fetch_data',wraps=qt.fetch_data) as fetch:
                QTest.keyClick(w.search_edit,Qt.Key_V,Qt.ControlModifier)
            self.assertEqual(w.search_edit.text(),'1, 3')
            self.assertEqual({w.table.item(row,1).text() for row in range(w.table.rowCount())},{'1','3'})
            fetch.assert_called_once()
            self.assertNotIn('\n',w.filter_chips.text())
