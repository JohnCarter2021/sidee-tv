"""Manual update check: version parsing, release comparison, API route."""
import json
import tempfile
import unittest
from unittest.mock import patch

from core import update_check, webui
from tools.smoke_test import request


class TestParseVersion(unittest.TestCase):
    def test_plain_and_v_prefixed(self):
        self.assertEqual(update_check.parse_version("0.1.4.2"), (0, 1, 4, 2))
        self.assertEqual(update_check.parse_version("v0.1.4.3"), (0, 1, 4, 3))

    def test_malformed(self):
        self.assertIsNone(update_check.parse_version(""))
        self.assertIsNone(update_check.parse_version("1.2.x"))
        self.assertIsNone(update_check.parse_version("latest"))


class TestCheck(unittest.TestCase):
    def test_newer_release_is_offered(self):
        result = update_check.check(
            fetch=lambda: {"tag_name": "v0.2.0.2",
                           "html_url": "https://example.invalid/r/1"})
        self.assertEqual(result, {"ok": True, "current": "0.2.0.1",
                                  "latest": "0.2.0.2", "update_available": True,
                                  "url": "https://example.invalid/r/1"})

    def test_same_and_older_are_not_offered(self):
        for tag in ("v0.2.0.1", "v0.2.0.0", "v0.1.4.2"):
            result = update_check.check(fetch=lambda tag=tag: {"tag_name": tag})
            self.assertFalse(result["update_available"])
            self.assertEqual(result["url"], update_check.RELEASES_URL)

    def test_network_failure_is_a_plain_error(self):
        def boom():
            raise ConnectionError("offline")
        result = update_check.check(fetch=boom)
        self.assertFalse(result["ok"])
        self.assertIn("connection", result["error"])

    def test_malformed_release_is_a_plain_error(self):
        result = update_check.check(fetch=lambda: {"tag_name": "banana"})
        self.assertFalse(result["ok"])


class TestUpdateApi(unittest.TestCase):
    def test_api_update_returns_check_result(self):
        canned = {"ok": True, "current": "0.2.0.0", "latest": "0.1.5.0",
                  "update_available": True, "url": "https://example.invalid/r/1"}
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(__import__("os").environ, {"SIDEE_STATE_DIR": directory}), \
                patch.object(update_check, "check", return_value=canned):
            dashboard = webui.Dashboard(port=0)
            try:
                dashboard.start()
                status, _, body = request(
                    dashboard.port, "/api/update?key=" + webui.ACCESS_KEY)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), canned)
            finally:
                dashboard.close()


if __name__ == "__main__":
    unittest.main()
