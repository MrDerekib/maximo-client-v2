import hashlib
import io
import threading
import zipfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from tests.test_support import temporary_directory
from update_checker import LatestRelease, UpdateDownloadCancelled, download_release_asset
from update_installer import distributed_executable


class UpdatePackageTests(TestCase):
    def package(self, filename="MaximoDesktop/MaximoDesktop.exe"):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr(filename, b"test executable")
        contents = archive.getvalue()
        release = LatestRelease("v1.0.0", "", "", "https://example.test/app.zip", f"sha256:{hashlib.sha256(contents).hexdigest()}")
        response = io.BytesIO(contents)
        response.headers = {"Content-Length": str(len(contents))}
        return release, response

    def test_verified_package_returns_executable_directory(self):
        release, response = self.package()
        with temporary_directory() as directory, patch("update_checker.urllib.request.urlopen", return_value=response):
            source = download_release_asset(release, Path(directory) / "update")
            self.assertEqual(source.name, "MaximoDesktop")
            self.assertTrue((source / "MaximoDesktop.exe").is_file())

    def test_bad_digest_is_rejected_before_extracting(self):
        release, response = self.package()
        release.asset_digest = "sha256:" + "0" * 64
        with temporary_directory() as directory, patch("update_checker.urllib.request.urlopen", return_value=response):
            destination = Path(directory) / "update"
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                download_release_asset(release, destination)
            self.assertFalse((destination / "files").exists())

    def test_package_cannot_write_outside_cache(self):
        release, response = self.package("../MaximoDesktop.exe")
        with temporary_directory() as directory, patch("update_checker.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "ruta no válida"):
                download_release_asset(release, Path(directory) / "update")
            self.assertFalse((Path(directory) / "MaximoDesktop.exe").exists())

    def test_cancelled_download_does_not_contact_server(self):
        release, _ = self.package()
        cancel = threading.Event()
        cancel.set()
        with temporary_directory() as directory, patch("update_checker.urllib.request.urlopen") as request:
            with self.assertRaises(UpdateDownloadCancelled):
                download_release_asset(release, Path(directory) / "update", cancel_event=cancel)
            request.assert_not_called()

    def test_python_development_script_is_not_installable(self):
        with temporary_directory() as directory:
            script = Path(directory) / "ui_qt.py"
            script.write_text("", encoding="utf-8")
            with patch("update_installer.sys.argv", [str(script)]):
                self.assertIsNone(distributed_executable())

    def test_distributed_executable_is_detected(self):
        with temporary_directory() as directory:
            executable = Path(directory) / "MaximoDesktop.exe"
            executable.write_bytes(b"test")
            with patch("update_installer.sys.argv", [str(executable)]):
                self.assertEqual(distributed_executable(), executable.resolve())
