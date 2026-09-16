import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import maintenance as m


class MaintenanceTests(unittest.TestCase):
    def test_retention_keeps_latest_five_recent_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = time.time()
            exports = []
            for i in range(9):
                path = root / f"{i:08}.xls"
                path.write_bytes(b"old")
                os.utime(path, (now - (i + 2) * m.DAY,) * 2)
                exports.append(path)
            recent = root / ("maximo-export-" + "a" * 32 + ".xls")
            recent.write_bytes(b"recent")
            protected = [root / name for name in ("maximo_data.db", "personal.xls", "config.json", "notes.txt")]
            for path in protected:
                path.write_bytes(b"keep")
            removed, freed = m.cleanup_exports(root, now=now)
            self.assertEqual((removed, freed), (5, 15))
            self.assertTrue(recent.exists())
            self.assertTrue(all(path.exists() for path in exports[:4] + protected))
            self.assertTrue(all(not path.exists() for path in exports[4:]))

    def test_all_exports_under_one_day_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(10):
                (root / f"{i:08}.xls").write_bytes(b"recent")
            self.assertEqual(m.cleanup_exports(root), (0, 0))

    def test_links_are_not_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            linked = root / "12345678.xls"
            linked.write_bytes(b"keep")
            original = m._is_link
            with patch.object(m, "_is_link", side_effect=lambda path: path == linked or original(path)):
                self.assertEqual(m.cleanup_exports(root), (0, 0))
            self.assertTrue(linked.exists())

    def test_no_process_visibility_means_no_temp_deletion(self):
        with patch.object(m, "_edge_commands", return_value=None), patch.object(m.shutil, "rmtree") as remove:
            self.assertEqual(m.cleanup_stale_temps("."), (0, 0))
            remove.assert_not_called()

    def test_old_unused_temp_removed_but_active_recent_and_unknown_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = time.time()
            names = ["maximo-ot-abcdefgh", "maximo-ot-12345678", "maximo-update-abcdefgh", "other-folder"]
            folders = [root / name for name in names]
            for folder in folders:
                folder.mkdir()
                (folder / "cache").write_bytes(b"cache")
                os.utime(folder, (now - 10 * m.DAY,) * 2)
            os.utime(folders[2], (now, now))
            command = f'msedge.exe --user-data-dir="{folders[1]}"'.replace("/", "\\").casefold()
            with patch.object(m.tempfile, "gettempdir", return_value=str(root)), \
                 patch.object(m, "_edge_commands", return_value=[command]):
                self.assertEqual(m.cleanup_stale_temps(root, now), (1, 5))
            self.assertFalse(folders[0].exists())
            self.assertTrue(all(folder.exists() for folder in folders[1:]))

    def test_nested_link_prevents_recursive_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "maximo-ot-abcdefgh"
            folder.mkdir()
            child = folder / "junction"
            child.mkdir()
            now = time.time()
            os.utime(folder, (now - 10 * m.DAY,) * 2)
            original = m._is_link
            with patch.object(m.tempfile, "gettempdir", return_value=str(root)), \
                 patch.object(m, "_edge_commands", return_value=[]), \
                 patch.object(m, "_is_link", side_effect=lambda path: path == child or original(path)):
                self.assertEqual(m.cleanup_stale_temps(root, now), (0, 0))
            self.assertTrue(folder.exists())

    def test_unreadable_process_command_disables_cleanup(self):
        result = type("Result", (), {"stdout": '{"ProcessId":1,"CommandLine":null}'})()
        with patch.object(m.subprocess, "run", return_value=result):
            if os.name == "nt":
                self.assertIsNone(m._edge_commands())


if __name__ == "__main__":
    unittest.main()
