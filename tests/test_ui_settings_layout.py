"""Settings must shrink and expand without retaining the previous fixed width."""
import tests  # Isolate application data before importing product modules.
from unittest import TestCase
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
