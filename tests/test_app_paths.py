import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app_paths


class ProgramDirectoryTests(unittest.TestCase):
    def test_uses_executable_directory_when_runtime_directory_lacks_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_dir = root / "runtime-temp"
            executable_dir = root / "release"
            runtime_dir.mkdir()
            extension = executable_dir / "browser_extension"
            extension.mkdir(parents=True)
            (extension / "manifest.json").write_text("{}", encoding="utf-8")
            executable = executable_dir / "MaximoDesktop.exe"
            executable.touch()

            with patch.dict(
                app_paths.__dict__,
                {"__compiled__": SimpleNamespace(containing_dir=runtime_dir)},
            ), patch.object(app_paths.sys, "argv", [str(executable)]):
                self.assertEqual(app_paths._program_dir(), executable_dir.resolve())


if __name__ == "__main__":
    unittest.main()
