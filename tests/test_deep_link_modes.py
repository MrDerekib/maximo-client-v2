import tests
import sqlite3
import unittest
from unittest.mock import patch
from tests import test_filters as fixtures
from deep_links import make_ot_uri, parse_ot_uri, parse_ot_action

class DeepLinkModesTests(unittest.TestCase):
    def test_roundtrip_and_invalid_actions(self):
        for development in (False, True):
            for action in ("open", "open_filter", "filter"):
                uri = make_ot_uri("4448382", development, action)
                self.assertEqual(parse_ot_uri(uri), "4448382")
                self.assertEqual(parse_ot_action(uri), action)
        self.assertEqual(make_ot_uri("4448382"), "maximodesk://ot/4448382")
        for query in ("action=close", "action=", "action=filter&action=open", "other=filter", "action=filter#close"):
            self.assertIsNone(parse_ot_uri("maximodesk://ot/4448382?" + query))

    def test_modes_filter_exact_ot_clear_conflicting_filters_and_do_not_execute(self):
        for action in ("open", "open_filter", "filter"):
            with self.subTest(action=action):
                f = fixtures.FilterTests("runTest");f.setUp()
                try:
                    with sqlite3.connect(f.path) as conn:
                        conn.execute("INSERT INTO maximo (OT,Cliente) VALUES ('11','TMB')")
                    with f.qt_window() as (w, qt):
                        w.search_edit.setText("different")
                        w.advanced_state["tracking"] = ["RETENIDO"]
                        with qt.QSignalBlocker(w.priority_only_button):
                            w.priority_only_button.setChecked(True)
                        with patch.object(w, "open_ot_number") as opener, patch.object(w, "activate_window"):
                            w.handle_deep_link(make_ot_uri("1", action=action))
                        if action == "filter": opener.assert_not_called()
                        else: opener.assert_called_once_with("1")
                        if action != "open":
                            self.assertEqual(w.search_field(), "OT")
                            self.assertEqual(w.search_edit.text(), "1")
                            self.assertEqual([w.table.item(r,1).text() for r in range(w.table.rowCount())], ["1"])
                            self.assertFalse(w.priority_only_button.isChecked())
                            self.assertFalse(w.advanced_state["tracking"])
                            self.assertEqual(w._workorder_selector.selected_rows(), [])
                            w.search_edit.setText("");w.refresh_table()
                            self.assertEqual(w.table.rowCount(), 5)
                        else:
                            self.assertEqual(w.search_edit.text(), "different")
                finally: f.doCleanups()

    def test_missing_ot_and_invalid_uri_do_not_open_browser(self):
        f=fixtures.FilterTests("runTest");f.setUp()
        try:
            with f.qt_window() as (w, qt):
                with patch.object(w,"open_ot_number") as opener, patch.object(w,"activate_window"):
                    w.handle_deep_link(make_ot_uri("999",action="filter"))
                    self.assertEqual(w.table.rowCount(),0)
                    self.assertIn("no está en el listado local",w.status.currentMessage())
                    w.handle_deep_link("maximodesk://ot/1?action=close")
                    self.assertEqual(w.search_edit.text(),"999")
                opener.assert_not_called()
        finally:f.doCleanups()
