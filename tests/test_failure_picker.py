"""Conditional choices in settings cannot retain descendants from another path."""
import os
from unittest import TestCase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from config import AppConfig
from failure_catalog import choices, default_selection, resolve_selection
from failure_picker import FailurePathPicker


class FailurePickerTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.picker = FailurePathPicker()

    def tearDown(self):
        self.picker.deleteLater()
        self.app.processEvents()

    def test_previous_default_round_trips_without_editing(self):
        spec = default_selection()
        self.picker.set_selection(spec)
        self.assertEqual(self.picker.selection(), spec)
        self.assertEqual([node["code"] for node in resolve_selection(spec)["path"]],
                         ["OTROS-01", "OTROS-02", "OTROS-03"])

    def test_changing_class_clears_all_descendants_and_requires_new_choice(self):
        self.picker.set_selection(default_selection())
        index = self.picker.class_combo.findData("TRANSPORTES|LG-01")
        self.picker.class_combo.setCurrentIndex(index)
        self.assertEqual(self.picker.selection()["option_keys"], [])
        self.assertEqual(len(self.picker._levels), 1)
        self.assertEqual(self.picker._levels[0][0], "Síntoma")
        with self.assertRaises(ValueError):
            resolve_selection(self.picker.selection())
        self.picker._levels[0][1].setCurrentIndex(1)
        self.assertEqual(len(resolve_selection(self.picker.selection())["path"]), 1)
        self.assertEqual(len(self.picker._levels), 1)

    def test_changing_an_ancestor_resets_the_selected_remedy(self):
        spec = default_selection()
        self.picker.set_selection(spec)
        self.picker._levels[0][1].setCurrentIndex(0)
        self.assertEqual(self.picker.selection()["option_keys"], [])
        self.assertEqual(len(self.picker._levels), 1)
        self.picker._levels[0][1].setCurrentIndex(1)
        self.assertEqual(len(self.picker._levels), 2)
        self.assertEqual(self.picker._levels[1][1].currentIndex(), 0)

    def test_class_with_direct_causes_has_no_problem_placeholder(self):
        self.picker.set_selection({"class_key": "TRANSPORTES|CD-19", "option_keys": []})
        self.assertEqual(self.picker._levels[0][0], "Causa")
        first = choices("TRANSPORTES|CD-19")[0]
        self.picker._levels[0][1].setCurrentIndex(
            self.picker._levels[0][1].findData(first["key"]))
        self.assertEqual(self.picker._levels[1][0], "Resolución")

    def test_invalid_stored_selection_is_preserved_and_never_replaced_by_default(self):
        for spec in ({"class_key": "missing", "option_keys": ["old"]},
                     {"class_key": "TRANSPORTES|RFN-70", "option_keys": None}):
            with self.subTest(spec=spec):
                self.picker.set_selection(spec)
                self.assertEqual(self.picker.selection(), spec)
                with self.assertRaises(ValueError):
                    resolve_selection(self.picker.selection())
                self.assertIn("revisión", self.picker.hint.text())

    def test_old_configuration_keeps_current_behavior_but_has_independent_selection(self):
        first, second = AppConfig(), AppConfig()
        self.assertEqual(first.workorder_start_mode, "configured")
        self.assertEqual(first.workorder_start_selection, default_selection())
        first.workorder_start_selection["option_keys"].clear()
        self.assertEqual(second.workorder_start_selection, default_selection())
