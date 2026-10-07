import sqlite3
import unittest
from contextlib import ExitStack, closing, contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import db
from search_filters import load_profiles, save_profiles, validate_filters
from tests.test_support import temporary_directory


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory()
        self.temp_path = self.temp.__enter__()
        self.addCleanup(self.temp.__exit__, None, None, None)
        self.path = Path(self.temp_path) / "data.db"
        self.backup_dir = Path(self.temp_path) / "backups"
        self.backup_patch = patch.object(db, "BACKUP_DIR", self.backup_dir)
        self.backup_patch.start()
        self.addCleanup(self.backup_patch.stop)
        self.connection_patch = patch.object(db, "get_connection", side_effect=lambda: sqlite3.connect(self.path))
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        db.init_db()
        with closing(sqlite3.connect(self.path)) as conn:
            conn.executemany("""INSERT INTO maximo (
                OT, Descripción, Nº_de_serie, Fecha, Cliente, Tipo_de_trabajo, Seguimiento, Planta
            ) VALUES (?,?,?,?,?,?,?,?)""", [
                ("1", "Radio cabina", "001", "2026-01-01", "TMB", "REP", "EN TALLER", "LAB"),
                ("2", "Radio cabina", "002", "2026-02-01", "TMB", "REP", "RETENIDO", "LAB"),
                ("3", "Radio taller", "003", "2026-03-01", "OTRO", "GAR", "EN TALLER", "LAB"),
                ("4", "Display 100%", "004", None, "TMB", "GAR", None, "LAB"),
            ])
            conn.commit()

    def ids(self, advanced, client="Todos"):
        return [row[0] for row in db.fetch_data("", "OT", client, advanced)]

    def test_client_and_tracking(self):
        self.assertEqual(self.ids({"tracking": ["EN TALLER"]}, "TMB"), ["1"])

    def test_import_normalizes_categories_and_repeat_has_no_changes(self):
        import pandas as pd
        frame = pd.DataFrame([("5", "Radio\u00a0cabina", "A\u00a0B", "2026-01-01",
                               " TMB\u00a0 SUR ", " REP  TALLER ", "DAR\u00a0SALIDA", "LAB")])
        self.assertEqual(db.update_database_from_df(frame), (1, 0))
        self.assertEqual(db.update_database_from_df(frame), (0, 0))
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute("SELECT * FROM maximo WHERE OT='5'").fetchone()
        self.assertEqual(row[1:3], ("Radio\u00a0cabina", "A\u00a0B"))
        self.assertEqual(row[4:7], ("TMB SUR", "REP TALLER", "DAR SALIDA"))
        frame.iloc[0, 6] = " EN\u00a0TALLER  "
        self.assertEqual(db.update_database_from_df(frame), (0, 1))
        self.assertEqual(self.ids({"tracking": ["EN TALLER"]}), ["1", "3", "5"])
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT Seguimiento FROM maximo WHERE OT='5'").fetchone()[0], "EN TALLER")

    def test_successful_import_marks_missing_rows_inactive_and_reactivates_them(self):
        import pandas as pd
        frame = pd.DataFrame([("1", "Radio cabina", "001", "2026-01-01", "TMB", "REP", "EN TALLER", "LAB")])
        db.update_database_from_df(frame)
        with closing(sqlite3.connect(self.path)) as conn:
            states = dict(conn.execute("SELECT OT, Activo FROM maximo"))
            last_seen = conn.execute("SELECT Ultima_vez_visto FROM maximo WHERE OT='1'").fetchone()[0]
        self.assertEqual(states["1"], 1)
        self.assertEqual(states["2"], 0)
        self.assertTrue(last_seen)

        restored = pd.DataFrame([("2", "Radio cabina", "002", "2026-02-01", "TMB", "REP", "RETENIDO", "LAB")])
        db.update_database_from_df(restored)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT Activo FROM maximo WHERE OT='2'").fetchone()[0], 1)

    def test_only_inactive_records_can_be_deleted(self):
        import pandas as pd
        db.update_database_from_df(pd.DataFrame([
            ("1", "Radio cabina", "001", "2026-01-01", "TMB", "REP", "EN TALLER", "LAB")
        ]))
        self.assertFalse(db.delete_inactive_record("1"))
        self.assertTrue(db.delete_inactive_record("2"))
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM maximo WHERE OT='2'").fetchone()[0], 0)

    def test_delete_all_inactive_records_keeps_active_rows(self):
        import pandas as pd
        db.update_database_from_df(pd.DataFrame([
            ("1", "Radio cabina", "001", "2026-01-01", "TMB", "REP", "EN TALLER", "LAB")
        ]))
        self.assertEqual(db.inactive_record_count(), 3)
        self.assertEqual(db.delete_all_inactive_records(), 3)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT OT FROM maximo ORDER BY OT").fetchall(), [("1",)])

    def test_inactive_tracking_candidates_are_reconciled_safely(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("UPDATE maximo SET Activo = 0, Seguimiento = 'EN TALLER' WHERE OT = '1'")
            conn.execute("UPDATE maximo SET Activo = 0, Seguimiento = 'APPR' WHERE OT = '2'")
            conn.execute("UPDATE maximo SET Activo = 0, Seguimiento = 'RETENIDO' WHERE OT = '3'")
            conn.commit()
        self.assertEqual(db.inactive_tracking_candidates(), [("1", "EN TALLER"), ("2", "APPR")])
        self.assertTrue(db.apply_reconciled_status("1", " DAR\u00a0SALIDA ", "2026-09-18T10:00:00"))
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT Seguimiento FROM maximo WHERE OT='1'").fetchone()[0], "DAR SALIDA")
            self.assertEqual(conn.execute("SELECT Ultima_comprobacion_estado FROM maximo WHERE OT='1'").fetchone()[0], "2026-09-18T10:00:00")
            self.assertEqual(conn.execute("SELECT Seguimiento FROM maximo WHERE OT='2'").fetchone()[0], "APPR")
        self.assertTrue(db.apply_reconciled_status("2", "DAR SALIDA"))
        self.assertFalse(db.apply_reconciled_status("3", "DAR SALIDA"))

    def test_priority_candidates_ignore_the_24_hour_cooldown(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "UPDATE maximo SET Activo = 0, Seguimiento = 'EN TALLER', Ultima_comprobacion_estado = ? WHERE OT = '1'",
                (datetime.now().isoformat(timespec="seconds"),),
            )
            conn.commit()
        self.assertEqual(db.inactive_tracking_candidates(), [])
        self.assertEqual(db.inactive_tracking_candidates(limit=None, minimum_age_hours=None), [("1", "EN TALLER")])

    def test_migration_preserves_original_backup_and_runs_once(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DELETE FROM client_migrations")
            conn.execute("UPDATE maximo SET Seguimiento = ? WHERE OT='1'", (" DAR\u00a0SALIDA ",))
            before = conn.execute("SELECT * FROM maximo ORDER BY OT").fetchall()
            conn.commit()
        db.init_db()
        backups = list(self.backup_dir.glob("*.db"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as conn:
            self.assertEqual(conn.execute("SELECT * FROM maximo ORDER BY OT").fetchall(), before)
        with closing(sqlite3.connect(self.path)) as conn:
            after = conn.execute("SELECT * FROM maximo ORDER BY OT").fetchall()
        expected = list(before[0])
        expected[6] = "DAR SALIDA"
        self.assertEqual(after, [tuple(expected)] + before[1:])
        db.init_db()
        self.assertEqual(list(self.backup_dir.glob("*.db")), backups)

    def test_failed_backup_leaves_original_data_and_allows_retry(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DELETE FROM client_migrations")
            conn.execute("UPDATE maximo SET Seguimiento = ? WHERE OT='1'", ("DAR\u00a0SALIDA",))
            conn.commit()
        with patch.object(db.Path, "mkdir", side_effect=PermissionError("backup blocked")):
            with self.assertRaises(PermissionError):
                db.init_db()
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT Seguimiento FROM maximo WHERE OT='1'").fetchone()[0], "DAR\u00a0SALIDA")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM client_migrations").fetchone()[0], 0)
        db.init_db()
        self.assertEqual(self.ids({"tracking": ["DAR SALIDA"]}), ["1"])

    def test_invisible_spaces_share_choice_and_match_all_rows(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("UPDATE maximo SET Seguimiento = ? WHERE OT = '1'", ("DAR SALIDA",))
            conn.execute("UPDATE maximo SET Seguimiento = ? WHERE OT = '2'", (" DAR\u00a0SALIDA  ",))
            conn.commit()
        self.assertEqual(db.filter_choices()["tracking"].count("DAR SALIDA"), 1)
        self.assertNotIn(" DAR\u00a0SALIDA  ", db.filter_choices()["tracking"])
        self.assertEqual(self.ids({"tracking": ["DAR SALIDA"]}), ["1", "2"])
        self.assertEqual(self.ids({"tracking": ["DAR\u00a0SALIDA"]}), ["1", "2"])
        self.assertEqual(validate_filters({"tracking": ["DAR SALIDA", "DAR\u00a0SALIDA"]})["tracking"], ["DAR SALIDA"])

    def test_equipment_type_and_multiple_tracking(self):
        self.assertEqual(self.ids({"equipment": "cabina radio", "types": ["REP"],
                                   "tracking": ["EN TALLER", "RETENIDO"]}), ["1", "2"])

    def test_advanced_clients_override_simple_client(self):
        self.assertEqual(self.ids({"clients": ["OTRO"], "tracking": ["EN TALLER"]}, "TMB"), ["3"])

    def test_dates_are_inclusive(self):
        self.assertEqual(self.ids({"date_from": "2026-01-01", "date_to": "2026-02-01"}), ["1", "2"])

    def test_empty_and_literal_wildcard(self):
        self.assertEqual(self.ids({"tracking": [""]}), ["4"])
        self.assertEqual(self.ids({"equipment": "%"}), ["4"])

    def test_invalid_dates_and_field_rejected(self):
        for filters in ({"date_from": "2026-02-30"}, {"date_from": "2026-03-01", "date_to": "2026-01-01"}):
            with self.assertRaises(ValueError):
                validate_filters(filters)
        with self.assertRaises(ValueError):
            db.fetch_data("", "OT; DROP TABLE maximo", "Todos")

    def test_choices_and_sql_values(self):
        self.assertIn("", db.filter_choices()["tracking"])
        self.assertEqual(self.ids({"clients": ["TMB' OR 1=1 --"]}), [])
        self.assertEqual(len(self.ids({})), 4)

    def test_profiles_roundtrip_and_delete(self):
        path = Path(self.temp_path) / "profiles.json"
        profile = {"search": "", "search_by": "OT", "client": "TMB",
                   "advanced": {"tracking": ["EN TALLER"]}}
        save_profiles(path, {"TMB pendientes": profile})
        loaded = load_profiles(path)["TMB pendientes"]
        self.assertEqual(self.ids(loaded["advanced"], loaded["client"]), ["1"])
        save_profiles(path, {})
        self.assertEqual(load_profiles(path), {})

    def test_invalid_profile_does_not_replace_existing_file(self):
        path = Path(self.temp_path) / "profiles.json"
        save_profiles(path, {})
        with self.assertRaises(ValueError):
            save_profiles(path, {"bad": {"search_by": "sql"}})
        self.assertEqual(load_profiles(path), {})

    @contextmanager
    def qt_window(self):
        import logging
        import os
        from config import AppConfig
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        with patch("logging.handlers.RotatingFileHandler", return_value=logging.NullHandler()), patch("logging.basicConfig"):
            import ui_qt
        FilterTests.qt_app = ui_qt.QApplication.instance() or ui_qt.QApplication([])
        with ExitStack() as patches:
            patches.enter_context(patch.object(ui_qt, "load_config", return_value=AppConfig()))
            patches.enter_context(patch.object(ui_qt, "save_config"))
            patches.enter_context(patch.object(ui_qt, "PROFILES_PATH", Path(self.temp_path) / "profiles.json"))
            patches.enter_context(patch.object(ui_qt, "DEVELOPMENT_MODE", False))
            patches.enter_context(patch.object(ui_qt.QTimer, "singleShot"))
            window = ui_qt.MaximoDesktopWindow()
            try:
                yield window, ui_qt
            finally:
                window._close_finalized = True
                window.close()
                window.deleteLater()

    def test_qt_window_initialization_and_combined_filter(self):
        with self.qt_window() as (window, qt):
            self.assertEqual(window.table.rowCount(), 4)
            self.assertIsNone(window.findChild(qt.QLabel, "developmentMode"))
            window.client_combo.set_options(["TMB", "OTRO"], ["TMB"])
            window.advanced_state["tracking"] = ["EN TALLER"]
            window.refresh_table()
            self.assertEqual(window.table.rowCount(), 1)
            self.assertEqual(window.table.item(0, 1).text(), "1")

    def test_qt_saved_profile_applies_filters_and_can_be_cleared(self):
        with self.qt_window() as (window, qt):
            name = "TMB pendientes"
            profile = {"search": "", "search_by": "OT", "client": "TMB",
                       "advanced": validate_filters({"tracking": ["EN TALLER"]})}
            save_profiles(Path(self.temp_path) / "profiles.json", {name: profile})
            window.refresh_profiles()
            item = window.profile_list.item(0)
            self.assertEqual(item.data(qt.Qt.UserRole), name)
            window.load_selected_profile(item)
            self.assertEqual(window.table.rowCount(), 1)
            self.assertIn("EN TALLER", window.filter_chips.text())
            self.assertEqual(window.current_profile_state()["advanced"]["tracking"], ["EN TALLER"])
            window.clear_filters()
            self.assertEqual(window.table.rowCount(), 4)
            self.assertEqual(window.advanced_state["tracking"], [])
