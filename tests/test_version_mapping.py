"""One version across platforms (plan section 7).

The dashboard's self-reported version and the Android versionName must
agree, so a release cannot ship with two different numbers by accident.
Windows/macOS/Linux CI builds derive their version from the tag or the
`release: v...` commit message; this test covers the two versions that
live in source.
"""
import re
import unittest
from pathlib import Path

from core import update_check

ROOT = Path(__file__).resolve().parent.parent


class TestVersionMapping(unittest.TestCase):
    def test_android_version_matches_core_version(self):
        gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text()
        name = re.search(r'versionName = "([^"]+)"', gradle).group(1)
        self.assertEqual(name, update_check.CURRENT_VERSION)

    def test_android_version_code_is_a_positive_integer(self):
        gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text()
        code = int(re.search(r"versionCode = (\d+)", gradle).group(1))
        self.assertGreater(code, 0)

    def test_release_notes_exist_for_current_version(self):
        self.assertTrue(
            (ROOT / "docs" / "releases"
             / (update_check.CURRENT_VERSION + ".md")).is_file(),
            "docs/releases/<version>.md must exist before a release")


if __name__ == "__main__":
    unittest.main()
