"""Row copying uses clipboard mocks only; no real clipboard is changed."""
import tests
import csv
from io import StringIO
from unittest import TestCase
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QTableWidget,QTableWidgetItem
from table_clipboard import row_copy_mime
from tests import test_filters as fixtures


class TableClipboardTests(TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def table(self):
        t=QTableWidget(3,3);t.setHorizontalHeaderLabels(['OT','Serie','Descripción'])
        for row,values in enumerate([('10001','001','Text <b> & \"quoted\"'),('10002','002','Line 1\nLine 2'),('10003','003','Hidden')]):
            for col,text in enumerate(values):t.setItem(row,col,QTableWidgetItem(text))
        self.addCleanup(t.deleteLater);return t

    def test_tsv_and_html_preserve_full_values_and_headers(self):
        t=self.table();mime=row_copy_mime(t,[1,0,0])
        rows=list(csv.reader(StringIO(mime.text()),delimiter='\t'))
        self.assertEqual(rows[0],['OT','Serie','Descripción'])
        self.assertEqual([r[0] for r in rows[1:]],['10001','10002'])
        self.assertEqual(rows[1][1],'001');self.assertEqual(rows[2][2],'Line 1\nLine 2')
        self.assertTrue(mime.hasHtml());self.assertIn('&lt;b&gt;',mime.html())
        self.assertNotIn('<b>',mime.html());self.assertIn('Line 1<br>Line 2',mime.html())

    def test_hidden_rows_columns_and_visual_column_order_are_respected(self):
        t=self.table();t.setRowHidden(2,True);t.setColumnHidden(2,True)
        t.horizontalHeader().moveSection(1,0)
        mime=row_copy_mime(t,[0,1,2])
        rows=list(csv.reader(StringIO(mime.text()),delimiter='\t'))
        self.assertEqual(rows,[['Serie','OT'],['001','10001'],['002','10002']])
        self.assertIsNone(row_copy_mime(t,[2]))

    def test_context_copies_single_row_or_marked_batch_without_clearing_marks(self):
        f=fixtures.FilterTests('runTest');f.setUp();self.addCleanup(f.doCleanups)
        with f.qt_window() as (w,qt):
            w.show();qt.QApplication.processEvents()
            for row in (0,1):w._workorder_selector._toggle_row(w.table.model().index(row,1),qt.Qt.NoModifier)
            marked=w._workorder_selector.selected_rows()
            for target,expected in [(0,2),(2,1)]:
                menu=qt.QMenu(w);clipboard=Mock()
                try:
                    position=w.table.visualRect(w.table.model().index(target,1)).center()
                    with patch.object(qt,'QMenu',return_value=menu),patch.object(menu,'exec'),patch.object(qt.QApplication,'clipboard',return_value=clipboard):
                        w.show_context_menu(position)
                        action=next(a for a in menu.actions() if a.text().startswith('Copiar fila completa') or a.text().startswith('Copiar 2 filas'))
                        action.trigger()
                    clipboard.setMimeData.assert_called_once()
                    rows=list(csv.reader(StringIO(clipboard.setMimeData.call_args.args[0].text()),delimiter='\t'))
                    self.assertEqual(len(rows),expected+1)
                    self.assertIn('OT',rows[0]);self.assertIn(w.table.item(target,1).text(),[r[1] for r in rows[1:]])
                    self.assertEqual(w._workorder_selector.selected_rows(),marked)
                finally:menu.deleteLater()

    def test_missing_or_filtered_rows_do_not_erase_clipboard(self):
        f=fixtures.FilterTests('runTest');f.setUp();self.addCleanup(f.doCleanups)
        with f.qt_window() as (w,qt):
            with patch.object(qt.QApplication,'clipboard') as clipboard:w.copy_rows(('missing',))
            clipboard.assert_not_called()
