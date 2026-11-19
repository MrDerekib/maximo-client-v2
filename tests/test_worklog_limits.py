import tests
from unittest import TestCase
from PySide6.QtWidgets import QApplication,QTableWidget,QTableWidgetItem,QStyleOptionViewItem
from worklog_limits import validate_worklog_summary,summary_length
from technician_repair_ui import WorklogSummaryDelegate
from technician_repair import reviewed_repair
from technician_sat import format_incident
from failure_catalog import default_selection
from warehouse import WarehouseItem

class WorklogLimitTests(TestCase):
    def test_native_boundary_and_unicode_length(self):
        for text in ('a'*100,'á'*100,'🚀'*50):
            self.assertEqual(summary_length(text),100)
            self.assertEqual(validate_worklog_summary(text),text)
        for text in ('a'*101,'á'*101,'🚀'*51):
            with self.assertRaisesRegex(ValueError,'100 caracteres'):validate_worklog_summary(text)

    def test_incident_prefix_is_counted_once(self):
        self.assertEqual(len(format_incident('x'*95)),100)
        self.assertEqual(format_incident('inc: '+'x'*95),'inc: '+'x'*95)
        with self.assertRaisesRegex(ValueError,'incluido «inc: »'):format_incident('x'*96)

    def test_long_summary_is_rejected_but_long_details_are_preserved(self):
        values={'reference':'stock','duration':'0,5','time_mode':'end','time':'2026-11-11T10:00:00',
            'action':'close','entries':[{'summary':'a'*100,'details':'Texto extenso '*1000}]}
        plan=reviewed_repair(WarehouseItem('TEST'),values,default_selection())
        self.assertEqual(plan.entries[0].details,values['entries'][0]['details'].strip())
        values['entries'][0]['summary']='a'*101
        with self.assertRaisesRegex(ValueError,'100 caracteres'):reviewed_repair(WarehouseItem('TEST'),values,default_selection())

    def test_editor_limits_new_input_and_preserves_oversized_existing_draft(self):
        app=QApplication.instance() or QApplication([])
        table=QTableWidget(1,1);table.setItem(0,0,QTableWidgetItem(''))
        delegate=WorklogSummaryDelegate(table);index=table.model().index(0,0)
        try:
            editor=delegate.createEditor(table,QStyleOptionViewItem(),index)
            delegate.setEditorData(editor,index);editor.insert('x'*101)
            self.assertEqual(editor.text(),'x'*100)
            delegate.setModelData(editor,table.model(),index)
            self.assertEqual(table.item(0,0).text(),'x'*100)
            table.item(0,0).setText('x'*120)
            delegate.setEditorData(editor,index)
            self.assertEqual(editor.text(),'x'*120)
            editor.setText('Corregido');delegate.setModelData(editor,table.model(),index)
            self.assertEqual(table.item(0,0).text(),'Corregido')
        finally:table.deleteLater();app.processEvents()

    def test_long_editor_does_not_cover_details_after_typing_or_resize(self):
        from PySide6.QtWidgets import QHeaderView,QLineEdit,QPlainTextEdit
        from technician_repair_ui import RepairDialog
        from unittest.mock import patch
        import ui_qt
        app=QApplication.instance() or QApplication([])
        with patch('technician_repair_ui.get_fault_description',return_value='Fallo ficticio'):
            dialog=RepairDialog(WarehouseItem('TEST'),default_selection(),autoload=False)
        try:
            dialog.add_entry('Prueba','Detalles que deben seguir visibles')
            dialog.show();app.processEvents()
            table=dialog.entries
            for theme,profile in (('light','normal'),('dracula','comfortable')):
                ui_qt.apply_application_theme(app,theme,profile)
                for width in (1050,800):
                    dialog.resize(width,900);app.processEvents()
                    table.editItem(table.item(0,0));app.processEvents()
                    editor=next(e for e in table.findChildren(QLineEdit) if e.isVisible())
                    editor.selectAll();editor.insert('x'*100);app.processEvents()
                    bounds=table.visualItemRect(table.item(0,0))
                    self.assertTrue(bounds.contains(editor.geometry()))
                    self.assertLess(editor.geometry().right(),table.columnViewportPosition(1))
                    self.assertEqual(table.cellWidget(0,1).toPlainText(),'Detalles que deben seguir visibles')
                    table.closePersistentEditor(table.item(0,0))
                    table.setFocus();app.processEvents()
        finally:dialog.hide();dialog.deleteLater();app.processEvents()
