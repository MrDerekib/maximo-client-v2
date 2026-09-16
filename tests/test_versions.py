import unittest
from update_checker import is_newer, format_version_tag


class VersionTests(unittest.TestCase):
    def test_revision_order(self):
        for remote, local in (("0.9.4.1", "0.9.4"), ("v0.9.4.10", "0.9.4.2"),
                              ("0.9.5", "0.9.4.99")):
            self.assertTrue(is_newer(remote, local))
            self.assertFalse(is_newer(local, remote))
        self.assertFalse(is_newer("0.9.4.0", "0.9.4"))
        self.assertFalse(is_newer("0.9.4.1", "0.9.4.1"))

    def test_display_preserves_revision_and_legacy_tags(self):
        for value, expected in (("release-0.9.4.1", "v0.9.4.1"),
                                ("v.0.9.4", "v0.9.4"), ("0.9", "v0.9.0")):
            self.assertEqual(format_version_tag(value), expected)
