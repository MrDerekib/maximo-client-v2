import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import maintenance as m
from tests.test_support import temporary_directory


class MaintenanceTests(unittest.TestCase):
    def test_retention_keeps_latest_five_recent_and_unrelated_files(self):
        with temporary_directory() as directory:
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
        with temporary_directory() as directory:
            root = Path(directory)
            for i in range(10):
                (root / f"{i:08}.xls").write_bytes(b"recent")
            self.assertEqual(m.cleanup_exports(root), (0, 0))

    def test_links_are_not_deleted(self):
        with temporary_directory() as directory:
            root = Path(directory)
            linked = root / "12345678.xls"
            linked.write_bytes(b"keep")
            original = m._is_link
            with patch.object(m, "_is_link", side_effect=lambda path: path == linked or original(path)):
                self.assertEqual(m.cleanup_exports(root), (0, 0))
            self.assertTrue(linked.exists())

if __name__ == "__main__":
    unittest.main()
