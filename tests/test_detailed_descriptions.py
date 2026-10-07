import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import db
import updater
from detailed_description import sanitize_detail_html


class DetailedDescriptionTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.gettempdir()) / f"maximo-detail-test-{uuid4().hex}"
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        database = self.folder / "maximo.db"
        connection_patch = patch.object(db, "get_connection", side_effect=lambda: sqlite3.connect(database))
        connection_patch.start()
        self.addCleanup(connection_patch.stop)
        db.init_db()
        with sqlite3.connect(database) as conn:
            conn.executemany(
                "INSERT INTO maximo (OT, Activo) VALUES (?, 1)", [("100",), ("200",)],
            )

    def test_full_and_empty_details_are_persisted_without_retries(self):
        self.assertEqual(db.detailed_description_candidates(), ["100", "200"])
        self.assertTrue(db.apply_detailed_description("100", "INC123\tFallo", "<table><tr><td>INC123</td></tr></table>"))
        self.assertTrue(db.apply_detailed_description("200", "", ""))
        self.assertEqual(db.detailed_description_candidates(), [])
        self.assertEqual(db.get_detailed_description("100")[0], "INC123\tFallo")
        self.assertEqual(db.get_detailed_description("200"), ("", ""))
        rows = db.fetch_data("", "OT", "Todos", include_sync=True, include_fault=True, include_detail=True)
        self.assertEqual({row[2]: row[-1] for row in rows}, {"100": 1, "200": 0})

    def test_markup_keeps_table_but_removes_active_content(self):
        html = sanitize_detail_html('<table style="width:999px"><tr><td onclick="evil()">INC123</td></tr></table><script>evil()</script><a href="https://example.com">texto</a>')
        self.assertIn("<table", html)
        self.assertIn("<td>INC123</td>", html)
        self.assertIn("texto", html)
        self.assertNotIn("onclick", html)
        self.assertNotIn("evil", html)
        self.assertNotIn("href", html)

    def test_detail_uses_the_same_loaded_ot_as_fault(self):
        driver = Mock()
        with patch.object(updater, "fault_description_candidates", return_value=["100"]), \
             patch.object(updater, "detailed_description_candidates", return_value=["100"]), \
             patch.object(updater, "create_edge_profile", return_value="C:/detail-profile"), \
             patch.object(updater, "setup_driver", return_value=driver), \
             patch.object(updater, "login"), patch.object(updater, "open_workorders_app"), \
             patch.object(updater, "read_workorder_fault_description", return_value="Fallo"), \
             patch.object(updater, "read_workorder_detailed_description", return_value=("INC123", "<p>INC123</p>")) as read_detail, \
             patch.object(updater, "apply_fault_description", return_value=True), \
             patch.object(updater, "apply_detailed_description", return_value=True), \
             patch.object(updater, "cleanup_edge_profile"):
            self.assertEqual(updater.enrich_fault_descriptions(include_detail=True), 2)
        read_detail.assert_called_once_with(driver, "100", already_loaded=True, cancel_event=None)
        driver.quit.assert_called_once()


    def test_plain_text_detail_is_preserved(self):
        content = "Correo Juncosa para creación: ma. 28/10/2025 12:45"
        self.assertEqual(sanitize_detail_html(content + "<!-- RICH TEXT -->"), content)

    def test_second_detail_refreshes_maximo_view(self):
        driver = Mock()
        with patch.object(updater, "detailed_description_candidates", return_value=["100", "200"]), \
             patch.object(updater, "create_edge_profile", return_value="C:/detail-profile"), \
             patch.object(updater, "setup_driver", return_value=driver), \
             patch.object(updater, "login"), \
             patch.object(updater, "open_workorders_app") as open_app, \
             patch.object(updater, "read_workorder_detailed_description", side_effect=[
                 ("Primera", "<p>Primera</p>"), ("Segunda", "<p>Segunda</p>")
             ]) as read_detail, \
             patch.object(updater, "apply_detailed_description", return_value=True), \
             patch.object(updater, "cleanup_edge_profile"):
            self.assertEqual(updater.enrich_fault_descriptions(include_fault=False, include_detail=True), 2)
        self.assertEqual(open_app.call_count, 2)
        driver.refresh.assert_called_once()
        self.assertEqual(read_detail.call_count, 2)

    def test_incomplete_popup_is_recovered_before_next_ot(self):
        driver = Mock()
        with patch.object(updater, "detailed_description_candidates", return_value=["100", "200"]), \
             patch.object(updater, "create_edge_profile", return_value="C:/detail-profile"), \
             patch.object(updater, "setup_driver", return_value=driver), \
             patch.object(updater, "login"), patch.object(updater, "open_workorders_app") as open_app, \
             patch.object(updater, "read_workorder_detailed_description", side_effect=[
                 RuntimeError("popup incompleto"), ("Texto", "Texto")
             ]), \
             patch.object(updater, "mark_detailed_description_attempt") as mark_attempt, \
             patch.object(updater, "apply_detailed_description", return_value=True), \
             patch.object(updater, "cleanup_edge_profile"):
            self.assertEqual(updater.enrich_fault_descriptions(include_fault=False, include_detail=True), 1)
        mark_attempt.assert_called_once_with("100")
        self.assertEqual(open_app.call_count, 2)
        driver.refresh.assert_called_once()


    def test_cancelled_read_leaves_remaining_ot_pending(self):
        from threading import Event

        driver = Mock()
        cancel = Event()

        def stop_on_first_read(*args, **kwargs):
            cancel.set()
            raise RuntimeError("Lectura cancelada")

        with patch.object(updater, "detailed_description_candidates", return_value=["100", "200"]), \
             patch.object(updater, "create_edge_profile", return_value="C:/detail-profile"), \
             patch.object(updater, "setup_driver", return_value=driver), \
             patch.object(updater, "login"), patch.object(updater, "open_workorders_app"), \
             patch.object(updater, "read_workorder_detailed_description", side_effect=stop_on_first_read) as read_detail, \
             patch.object(updater, "mark_detailed_description_attempt") as mark_attempt, \
             patch.object(updater, "cleanup_edge_profile"):
            self.assertEqual(updater.enrich_fault_descriptions(
                include_fault=False, include_detail=True, cancel_event=cancel,
            ), 0)
        read_detail.assert_called_once()
        mark_attempt.assert_not_called()
        driver.refresh.assert_not_called()
        driver.quit.assert_called_once()

    def test_three_consecutive_popup_errors_stop_the_batch(self):
        driver = Mock()
        with patch.object(updater, "detailed_description_candidates", return_value=["100", "200", "300", "400"]), \
             patch.object(updater, "create_edge_profile", return_value="C:/detail-profile"), \
             patch.object(updater, "setup_driver", return_value=driver), \
             patch.object(updater, "login"), patch.object(updater, "open_workorders_app"), \
             patch.object(updater, "read_workorder_detailed_description", side_effect=RuntimeError("popup incompleto")) as read_detail, \
             patch.object(updater, "mark_detailed_description_attempt") as mark_attempt, \
             patch.object(updater, "cleanup_edge_profile"):
            with self.assertRaisesRegex(RuntimeError, "3 fallos consecutivos"):
                updater.enrich_fault_descriptions(include_fault=False, include_detail=True)
        self.assertEqual(read_detail.call_count, 3)
        self.assertEqual(mark_attempt.call_count, 3)
        driver.quit.assert_called_once()



    def test_completed_read_is_saved_before_late_cancellation(self):
        from threading import Event

        driver = Mock()
        cancel = Event()

        def finish_then_cancel(*args, **kwargs):
            cancel.set()
            return "Detalle leído", "<p>Detalle leído</p>"

        with patch.object(updater, "detailed_description_candidates", return_value=["100", "200"]), \
             patch.object(updater, "create_edge_profile", return_value="C:/detail-profile"), \
             patch.object(updater, "setup_driver", return_value=driver), \
             patch.object(updater, "login"), patch.object(updater, "open_workorders_app"), \
             patch.object(updater, "read_workorder_detailed_description", side_effect=finish_then_cancel) as read_detail, \
             patch.object(updater, "apply_detailed_description", return_value=True) as save_detail, \
             patch.object(updater, "cleanup_edge_profile"):
            self.assertEqual(updater.enrich_fault_descriptions(
                include_fault=False, include_detail=True, cancel_event=cancel,
            ), 1)
        read_detail.assert_called_once()
        save_detail.assert_called_once_with("100", "Detalle leído", "<p>Detalle leído</p>")
        driver.quit.assert_called_once()

    def test_cancelled_wait_does_not_wait_for_timeout(self):
        from threading import Event
        from maximo_client import wait_for

        cancel = Event()
        cancel.set()
        condition = Mock()
        with self.assertRaisesRegex(RuntimeError, "cancelada"):
            wait_for(Mock(), condition, "prueba", timeout=20, cancel_event=cancel)
        condition.assert_not_called()



if __name__ == "__main__":
    unittest.main()
