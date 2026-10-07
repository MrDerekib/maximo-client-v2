"""Transiciones de la instalación Qt sin tocar la carpeta real del usuario."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import managed_install_qt as installer
from tests.test_support import temporary_directory


class QtManagedInstallTests(TestCase):
    def paths(self, root):
        external = root / "external"
        external.mkdir()
        executable = external / "MaximoDesktop.exe"
        executable.write_bytes(b"qt version")
        (external / "library.dll").write_bytes(b"dependency")
        managed = root / "app"
        return executable, managed

    @contextmanager
    def patched_install(self, root, executable, managed):
        with ExitStack() as stack:
            stack.enter_context(patch.object(installer, "APP_ROOT", root))
            stack.enter_context(patch.object(installer, "MANAGED_APP_DIR", managed))
            stack.enter_context(patch.object(installer, "DEVELOPMENT_MODE", False))
            stack.enter_context(patch.object(installer, "distributed_executable", return_value=executable))
            stack.enter_context(patch.object(installer, "ensure_user_directories"))
            stack.enter_context(patch.object(installer, "create_desktop_shortcut"))
            stack.enter_context(patch.object(installer.sys, "argv", [str(executable), "maximodesk://ot/4228010"]))
            yield stack.enter_context(patch.object(installer.subprocess, "Popen"))

    def test_first_install_copies_complete_package_and_preserves_data(self):
        with temporary_directory() as directory:
            root = Path(directory)
            executable, managed = self.paths(root)
            data = root / "data" / "maximo_data.db"
            data.parent.mkdir()
            data.write_bytes(b"local data")
            with self.patched_install(root, executable, managed) as launch:
                redirected = installer.redirect_to_managed_install()
            self.assertTrue(redirected)
            self.assertEqual((managed / "MaximoDesktop.exe").read_bytes(), b"qt version")
            self.assertEqual((managed / "library.dll").read_bytes(), b"dependency")
            self.assertEqual(data.read_bytes(), b"local data")
            self.assertFalse(list(root.glob(".app-staging-*")))
            launch.assert_called_once_with(
                [str(managed / "MaximoDesktop.exe"), "maximodesk://ot/4228010"], cwd=str(managed)
            )

    def test_newer_package_replaces_old_app_and_keeps_previous_copy(self):
        with temporary_directory() as directory:
            root = Path(directory)
            executable, managed = self.paths(root)
            managed.mkdir()
            (managed / "MaximoDesktop.exe").write_bytes(b"tk version")
            (managed / "old.dll").write_bytes(b"old dependency")

            def file_version(path):
                return (1, 0, 0, 0) if path == executable else (0, 9, 9, 4)

            with self.patched_install(root, executable, managed), \
                 patch.object(installer, "executable_file_version", side_effect=file_version):
                redirected = installer.redirect_to_managed_install()
            self.assertTrue(redirected)
            self.assertEqual((managed / "MaximoDesktop.exe").read_bytes(), b"qt version")
            previous = root / "app-previous-v0.9.9.4"
            self.assertEqual((previous / "MaximoDesktop.exe").read_bytes(), b"tk version")
            self.assertEqual((previous / "old.dll").read_bytes(), b"old dependency")

    def test_unknown_existing_version_keeps_installed_app(self):
        with temporary_directory() as directory:
            root = Path(directory)
            executable, managed = self.paths(root)
            managed.mkdir()
            (managed / "MaximoDesktop.exe").write_bytes(b"old version")
            with self.assertLogs(level="ERROR"), self.patched_install(root, executable, managed) as launch, \
                 patch.object(installer, "executable_file_version", return_value=None):
                with self.assertRaises(installer.ManagedInstallError):
                    installer.redirect_to_managed_install()
            self.assertEqual((managed / "MaximoDesktop.exe").read_bytes(), b"old version")
            launch.assert_not_called()
            self.assertFalse(list(root.glob(".app-staging-*")))

    def test_older_qt_package_does_not_silently_launch_tk_installation(self):
        with temporary_directory() as directory:
            root = Path(directory)
            executable, managed = self.paths(root)
            managed.mkdir()
            (managed / "MaximoDesktop.exe").write_bytes(b"newer installation")

            def file_version(path):
                return (0, 9, 9, 3) if path == executable else (0, 9, 9, 4)

            with self.assertLogs(level="ERROR"), self.patched_install(root, executable, managed) as launch, \
                 patch.object(installer, "executable_file_version", side_effect=file_version):
                with self.assertRaisesRegex(installer.ManagedInstallError, "más reciente"):
                    installer.redirect_to_managed_install()
            self.assertEqual((managed / "MaximoDesktop.exe").read_bytes(), b"newer installation")
            launch.assert_not_called()

    def test_python_development_does_not_install(self):
        with patch.object(installer, "distributed_executable", return_value=None), \
             patch.object(installer, "ensure_user_directories") as directories:
            self.assertFalse(installer.redirect_to_managed_install())
        directories.assert_not_called()

    def test_packaged_development_build_does_not_install(self):
        with patch.object(installer, "distributed_executable", return_value=Path("C:/build/MaximoDesktop.exe")), \
             patch.object(installer, "DEVELOPMENT_MODE", True), \
             patch.object(installer, "ensure_user_directories") as directories:
            self.assertFalse(installer.redirect_to_managed_install())
        directories.assert_not_called()
