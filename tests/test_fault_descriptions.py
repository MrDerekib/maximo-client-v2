import sqlite3
import shutil
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import db
import updater


class FaultDescriptionStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_path = Path(tempfile.gettempdir()) / f"maximo-fault-test-{uuid4().hex}"
        self.temp_path.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_path, ignore_errors=True)
        self.database = self.temp_path / "maximo.db"
        self.connection_patch = patch.object(db, "get_connection", side_effect=lambda: sqlite3.connect(self.database))
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        db.init_db()
        with closing(sqlite3.connect(self.database)) as conn:
            conn.executemany(
                """INSERT INTO maximo (OT, Descripción, Nº_de_serie, Fecha, Cliente, Tipo_de_trabajo,
                   Seguimiento, Planta, Activo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                [("100", "Equipo A", "A", "2026-01-01", "TMB", "REP", "EN TALLER", "LAB"),
                 ("200", "Equipo B", "B", "2026-01-01", "TMB", "REP", "EN TALLER", "LAB")],
            )
            conn.commit()

    def test_successful_read_is_persisted_and_not_repeated(self):
        self.assertEqual(db.fault_description_candidates(), ["100", "200"])
        self.assertTrue(db.apply_fault_description("100", "  PROVOCA\nCORTOCIRCUITO  ", "2026-09-25T10:00:00"))
        self.assertEqual(db.fault_description_candidates(), ["200"])
        with closing(sqlite3.connect(self.database)) as conn:
            row = conn.execute(
                "SELECT Descripcion_averia, Ultima_lectura_averia FROM maximo WHERE OT='100'"
            ).fetchone()
        self.assertEqual(row, ("PROVOCA CORTOCIRCUITO", "2026-09-25T10:00:00"))

    def test_failed_read_waits_while_other_work_is_available(self):
        self.assertTrue(db.mark_fault_description_attempt("100", datetime.now().isoformat(timespec="seconds")))
        self.assertEqual(db.fault_description_candidates(), ["200"])
        self.assertEqual(
            db.fault_description_candidates(limit=None, minimum_age_hours=None), ["200", "100"]
        )

    def test_failed_read_retries_when_it_is_the_only_pending_work(self):
        now = datetime.now().isoformat(timespec="seconds")
        self.assertTrue(db.mark_fault_description_attempt("100", now))
        self.assertTrue(db.mark_fault_description_attempt("200", now))
        self.assertEqual(db.fault_description_candidates(), ["100", "200"])


class FaultDescriptionUpdaterTests(unittest.TestCase):
    def test_enrichment_reuses_one_headless_session(self):
        driver = Mock()
        with patch.object(updater, "fault_description_candidates", return_value=["100", "200"]), \
             patch.object(updater, "create_edge_profile", return_value="C:/fault-profile"), \
             patch.object(updater, "setup_driver", return_value=driver) as setup, \
             patch.object(updater, "login"), patch.object(updater, "open_workorders_app"), \
             patch.object(updater, "read_workorder_fault_description", side_effect=["Avería A", "Avería B"]), \
             patch.object(updater, "apply_fault_description", return_value=True) as apply, \
             patch.object(updater, "cleanup_edge_profile") as cleanup:
            self.assertEqual(updater.enrich_fault_descriptions(), 2)
        setup.assert_called_once_with(headless=True, profile_dir="C:/fault-profile")
        self.assertEqual(apply.call_count, 2)
        driver.quit.assert_called_once()
        cleanup.assert_called_once_with("C:/fault-profile")
