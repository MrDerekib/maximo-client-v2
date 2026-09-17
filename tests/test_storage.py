import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import config
import credential_store
from tests.test_support import temporary_directory


class CredentialStoreTests(unittest.TestCase):
    def test_encrypted_credentials_round_trip_without_plaintext(self):
        with temporary_directory() as folder:
            path = Path(folder) / "credentials.dat"
            with patch.object(credential_store, "_protect", side_effect=lambda value: value[::-1]), \
                 patch.object(credential_store, "_unprotect", side_effect=lambda value: value[::-1]):
                credential_store.save_credentials("usuario-prueba", "secreto-prueba", path)
                self.assertNotIn(b"secreto-prueba", path.read_bytes())
                self.assertEqual(
                    credential_store.load_credentials(path),
                    ("usuario-prueba", "secreto-prueba"),
                )


class StorageMigrationTests(unittest.TestCase):
    def test_new_installation_copies_default_tracking_options(self):
        with temporary_directory() as folder:
            root = Path(folder)
            default = root / "program" / "seguimiento_options.txt"
            target = root / "MaximoDesktop" / "custom" / "seguimiento_options.txt"
            default.parent.mkdir()
            default.write_text("EN TALLER\nRETENIDO\n", encoding="utf-8")

            with patch.object(config, "DEFAULT_TRACKING_OPTIONS_PATH", default), \
                 patch.object(config, "TRACKING_OPTIONS_PATH", target):
                config._ensure_tracking_options()

            self.assertEqual(target.read_text(encoding="utf-8"), "EN TALLER\nRETENIDO\n")

    def test_migration_copies_and_verifies_data_and_removes_plaintext_secrets(self):
        with temporary_directory() as folder:
            root = Path(folder)
            legacy_root = root / "program"
            old_data = root / "old-data"
            target = root / "MaximoDesktop"
            legacy_root.mkdir()
            old_data.mkdir()
            old_db = old_data / "maximo_data.db"
            with closing(sqlite3.connect(old_db)) as connection:
                connection.execute("CREATE TABLE maximo (OT TEXT PRIMARY KEY)")
                connection.executemany("INSERT INTO maximo VALUES (?)", [("1",), ("2",)])
                connection.commit()
            (old_data / "search_profiles.json").write_text('{"Pendientes": {}}', encoding="utf-8")
            (old_data / "backups").mkdir()
            (old_data / "backups" / "previous.db").write_bytes(b"backup")
            (legacy_root / "seguimiento_options.txt").write_text("EN TALLER", encoding="utf-8")
            legacy_config = legacy_root / "config.json"
            legacy_config.write_text(json.dumps({
                "username": "usuario-secreto",
                "password": "clave-secreta",
                "db_path": str(old_db),
                "auto_update_enabled": True,
            }), encoding="utf-8")
            legacy_log = legacy_root / "maximo_client.log"
            legacy_log.write_text("usuario-secreto clave-secreta", encoding="utf-8")

            config_path = target / "config" / "config.json"
            db_path = target / "data" / "maximo_data.db"
            profiles_path = target / "data" / "search_profiles.json"
            backup_dir = target / "backups"
            tracking_path = target / "custom" / "seguimiento_options.txt"
            log_dir = target / "logs"
            credentials = {}

            def save_fake(username, password):
                credentials["value"] = (username, password)

            patches = (
                patch.object(config, "BASE_DIR", legacy_root),
                patch.object(config, "LEGACY_CONFIG_PATH", legacy_config),
                patch.object(config, "CONFIG_PATH", config_path),
                patch.object(config, "DB_PATH", db_path),
                patch.object(config, "PROFILES_PATH", profiles_path),
                patch.object(config, "BACKUP_DIR", backup_dir),
                patch.object(config, "TRACKING_OPTIONS_PATH", tracking_path),
                patch.object(config, "LOG_DIR", log_dir),
                patch.object(config, "DOWNLOAD_DIR", target / "cache" / "downloads"),
                patch.object(config, "EXPORT_DIR", target / "cache" / "exports"),
                patch.object(config, "ensure_user_directories", lambda: None),
                patch.object(config, "save_credentials", side_effect=save_fake),
                patch.object(config, "load_credentials", side_effect=lambda: credentials.get("value", ("", ""))),
            )
            for item in patches:
                item.start()
                self.addCleanup(item.stop)

            config._migrate_legacy_storage()
            config._sanitize_legacy_artifacts()
            with closing(sqlite3.connect(db_path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM maximo").fetchone()[0], 2)
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertTrue(profiles_path.exists())
            self.assertTrue((backup_dir / "previous.db").exists())
            self.assertEqual(tracking_path.read_text(encoding="utf-8"), "EN TALLER")
            self.assertNotIn("username", json.loads(config_path.read_text(encoding="utf-8")))
            sanitized = legacy_config.read_text(encoding="utf-8")
            self.assertNotIn("usuario-secreto", sanitized)
            self.assertNotIn("clave-secreta", sanitized)
            self.assertNotIn("usuario-secreto", legacy_log.read_text(encoding="utf-8"))
            self.assertNotIn("clave-secreta", legacy_log.read_text(encoding="utf-8"))

            # Al existir ya la configuración nueva, una segunda ejecución no repite la migración.
            config._migrate_legacy_storage()
            config._sanitize_legacy_artifacts()
            with closing(sqlite3.connect(db_path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM maximo").fetchone()[0], 2)
