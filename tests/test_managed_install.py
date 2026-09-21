import unittest

from managed_install import _format_file_version, _version_is_newer


class ManagedInstallTests(unittest.TestCase):
    def test_newer_embedded_version_replaces_managed_copy(self):
        self.assertTrue(_version_is_newer((0, 9, 9, 3), (0, 9, 9, 2)))
        self.assertTrue(_version_is_newer((1, 0, 0, 0), (0, 9, 9, 99)))

    def test_equal_or_older_embedded_version_does_not_replace_managed_copy(self):
        installed = (0, 9, 9, 3)
        self.assertFalse(_version_is_newer(installed, installed))
        self.assertFalse(_version_is_newer((0, 9, 9, 2), installed))

    def test_version_display_omits_unused_fourth_component(self):
        self.assertEqual(_format_file_version((0, 9, 9, 3)), "0.9.9.3")
        self.assertEqual(_format_file_version((0, 9, 9, 0)), "0.9.9")
