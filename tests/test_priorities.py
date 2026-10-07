import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import db


class PriorityStorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.gettempdir()) / f"maximo-priorities-{uuid4().hex}"
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.database = self.folder / "maximo.db"
        self.connection_patch = patch.object(db, "get_connection", side_effect=lambda: sqlite3.connect(self.database))
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        db.init_db()

    def test_replacing_a_project_keeps_history_and_changes_current_photo(self):
        db.replace_priority_snapshot(
            "TMB", "2026-09-28", "2026-09-28", "2026-09-25", ["tmb.xls"],
            [("100", None), ("200", None)],
        )
        self.assertEqual(db.current_priority_ots("2026-09-28"), {"100", "200"})
        db.replace_priority_snapshot(
            "TMB", "2026-09-29", "2026-09-29", "2026-09-29", ["tmb-new.xls"],
            [("200", None), ("300", None)],
        )
        self.assertEqual(db.current_priority_ots("2026-09-29"), {"200", "300"})
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM priority_snapshots").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM priority_snapshots WHERE is_current = 1").fetchone()[0], 1)

    def test_expiration_and_removal_hide_a_current_snapshot(self):
        db.replace_priority_snapshot(
            "RENFE", "2026-09-25", "2026-10-02", "2026-09-25", ["renfe.xls"],
            [("4267852", None)],
        )
        self.assertEqual(db.current_priority_ots("2026-09-29"), {"4267852"})
        self.assertTrue(db.update_priority_expiration("RENFE", "2026-09-28"))
        self.assertEqual(db.current_priority_ots("2026-09-29"), set())
        self.assertTrue(db.clear_current_priority_snapshot("RENFE"))
        self.assertEqual(db.current_priority_snapshots("2026-09-29"), [])

    def test_duplicate_ot_is_stored_once(self):
        db.replace_priority_snapshot(
            "Línea 9", "2026-09-29", "2026-09-29", None, ["l9.xls"],
            [("4216247", "Tramo I"), ("4216247", "Tramo II")],
        )
        snapshot = db.current_priority_snapshots("2026-09-29")[0]
        self.assertEqual(snapshot["item_count"], 1)

