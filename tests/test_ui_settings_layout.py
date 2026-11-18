"""Settings must shrink and expand without retaining the previous fixed width."""
import tests  # Isolate application data before importing product modules.
from unittest import TestCase
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QBoxLayout
from tests.test_ui_workorder_start import settings_window


class SettingsLayoutTests(TestCase):
    def test_settings_can_stack_then_return_to_two_columns(self):
        app = QApplication.instance() or QApplication([])
        window = settings_window()
        window._column_widths = None
        try:
            window.show()
            for width, expected in ((1440, QBoxLayout.LeftToRight),
                                    (850, QBoxLayout.TopToBottom),
                                    (1440, QBoxLayout.LeftToRight)):
                with self.subTest(width=width):
                    window.resize(width, 980)
                    app.processEvents()
                    window._update_settings_content_width()
                    app.processEvents()
                    self.assertEqual(window.settings_columns.direction(), expected)
                    self.assertLessEqual(window.settings_center.width(), 1280)
                    self.assertLessEqual(window.settings_center.width(), window.settings_scroll.viewport().width())
        finally:
            window.deleteLater(); app.processEvents()


    def test_tabs_group_every_setting_without_duplicating_widgets(self):
        app=QApplication.instance() or QApplication([])
        window=settings_window()
        try:
            self.assertEqual([window.settings_tabs.tabText(i) for i in range(4)],
                ['General','Datos y sincronización','Técnico y extensión','Almacén'])
            for index, names in enumerate((
                ('access_card','app_updates_card','appearance_card'),
                ('sync_card','maintenance_card','fault_descriptions_card','priorities_card','paths_card'),
                ('edge_extension_card','printing_card','technician_sat_card'),
                ('warehouse_card',))):
                page=window.settings_tabs.widget(index)
                for name in names:self.assertTrue(page.isAncestorOf(getattr(window,name)),name)
            self.assertTrue(window.sync_card.isAncestorOf(window.auto_check))
            self.assertFalse(window.access_card.isAncestorOf(window.auto_check))
            self.assertFalse(window.settings_tabs.isAncestorOf(window.save_settings_button))
        finally:window.deleteLater();app.processEvents()

    def test_tab_changes_keep_unsaved_values_and_global_save_clears_notice(self):
        app=QApplication.instance() or QApplication([])
        window=settings_window()
        try:
            with patch('ui_qt.save_config') as save:
                window.user_edit.setText('usuario-de-prueba')
                window.auto_check.setChecked(True)
                window.warehouse_check.setChecked(True)
                for index in (1,2,3,0):window.settings_tabs.setCurrentIndex(index)
                self.assertEqual(window.user_edit.text(),'usuario-de-prueba')
                self.assertTrue(window.auto_check.isChecked());self.assertTrue(window.warehouse_check.isChecked())
                self.assertIn('sin guardar',window.settings_save_hint.text())
                save.assert_not_called()
                self.assertTrue(window.save_settings(show_feedback=False))
                self.assertEqual(save.call_args.args[0].username,'usuario-de-prueba')
                self.assertTrue(save.call_args.args[0].auto_update_enabled)
                self.assertTrue(save.call_args.args[0].warehouse_enabled)
                self.assertFalse(window.settings_dirty())
                self.assertNotIn('sin guardar',window.settings_save_hint.text())
        finally:window.deleteLater();app.processEvents()

    def test_all_tabs_resize_and_footer_does_not_scroll(self):
        app=QApplication.instance() or QApplication([])
        window=settings_window();window._column_widths=None
        try:
            window.resize(1440,720);window.show();app.processEvents()
            for index in range(4):
                window.settings_tabs.setCurrentIndex(index);app.processEvents()
                window._update_settings_content_width();app.processEvents()
                self.assertLessEqual(window.settings_center.width(),window.settings_scroll.viewport().width())
                position=window.save_settings_button.mapTo(window,window.save_settings_button.rect().topLeft())
                window.settings_scroll.verticalScrollBar().setValue(window.settings_scroll.verticalScrollBar().maximum())
                app.processEvents()
                self.assertEqual(window.save_settings_button.mapTo(window,window.save_settings_button.rect().topLeft()),position)
        finally:window.deleteLater();app.processEvents()
