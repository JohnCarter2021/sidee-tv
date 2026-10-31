"""Sidee TV preset, identity persistence, and the auto-tile thread.

The auto tile is the zero-touch path: launch the app and the paired TV
gains (or refreshes) a Sidee TV tile pointing at this run's /tv/ menu.
No URL is ever typed on the TV, and no manual reinstall is needed when
the dashboard restarts.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import catalog, tv_frontend, webui


class SideeTvPresetTest(unittest.TestCase):
    def test_preset_record(self):
        app = catalog.get_app("sidee_tv")
        self.assertIsNotNone(app)
        self.assertEqual(app["app_id"], "sidee_tv")
        self.assertEqual(app["name"], "Sidee TV")
        self.assertEqual(app["category"], "Media")
        self.assertEqual(app["icon"], "assets/sidee-logo.png")
        # No static URL and no tile icon: the URL is built from the live
        # dashboard at install time, and tile icons must be HTTPS while
        # the dashboard serves plain HTTP on the LAN.
        self.assertEqual(app["url"], "")
        self.assertEqual(app["image"], "")

    def test_resolve_url_refuses_cli_install(self):
        app = catalog.get_app("sidee_tv")
        with self.assertRaises(ValueError) as caught:
            catalog.resolve_url(app, None)
        self.assertIn("running dashboard", str(caught.exception))

    def test_absolute_tv_url(self):
        key = "aB3_dEf6hIj9kLm0nOpQr"
        self.assertEqual(
            tv_frontend.absolute_tv_url("192.168.1.20", 8787, key),
            "http://192.168.1.20:8787/tv/?key=" + key)


class IdentityTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = patch.dict(os.environ,
                             {"SIDEE_STATE_DIR": self.directory.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_roundtrip_and_rejects_bad_files(self):
        self.assertEqual(webui._load_identity(), {})
        webui._save_identity("aB3_dEf6hIj9kLm0nOpQr", 8787)
        self.assertEqual(webui._load_identity(),
                         {"key": "aB3_dEf6hIj9kLm0nOpQr", "port": 8787})
        path = Path(webui._identity_path())
        # Windows chmod cannot enforce owner-only permissions (it reports
        # 0o666), so the mode check is Unix-only, matching the custom-apps
        # test's certificate-file check.
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        path.write_text("not json{")
        self.assertEqual(webui._load_identity(), {})
        path.write_text(json.dumps({"key": "short", "port": 8787}))
        self.assertEqual(webui._load_identity(), {})
        path.write_text(json.dumps({"key": "aB3_dEf6hIj9kLm0nOpQr",
                                    "port": 99999}))
        self.assertEqual(webui._load_identity(), {})

    def test_dashboard_start_persists_identity(self):
        dashboard = webui.Dashboard(port=0)
        try:
            dashboard.start()
            saved = webui._load_identity()
            self.assertEqual(saved["key"], webui.ACCESS_KEY)
            self.assertEqual(saved["port"], dashboard.port)
        finally:
            dashboard.close()
            dashboard.server.server_close()


class EnsureTileTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = patch.dict(os.environ,
                             {"SIDEE_STATE_DIR": self.directory.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dashboard = webui.Dashboard(port=0)
        self.addCleanup(self.dashboard.close)
        self.addCleanup(self.dashboard.server.server_close)
        self.session = Mock()
        self.session.host = "192.168.1.5"
        self.load_mock = self._start_patch(webui.client.Session, "load",
                                           return_value=self.session)
        self.snapshot = self._start_patch(webui.client,
                                          "applist_snapshot")
        self.add_tile = self._start_patch(webui.client, "add_tile")
        self._start_patch(webui, "_local_ip",
                          return_value="192.168.1.20")

    def _start_patch(self, target, attribute, **kwargs):
        patcher = patch.object(target, attribute, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def _expected_url(self):
        return tv_frontend.absolute_tv_url(
            "192.168.1.20", self.dashboard.port, webui.ACCESS_KEY)

    def test_installs_when_missing(self):
        self.snapshot.return_value = []
        self.dashboard._ensure_sidee_tv_tile_once()
        self.add_tile.assert_called_once_with(
            self.session, "sidee_tv", "Sidee TV", self._expected_url(), "")
        self.assertEqual(self.dashboard.tile_status["state"], "installed")
        self.assertEqual(self.dashboard.tile_status["url"],
                         self._expected_url())

    def test_skips_when_current_tile_present(self):
        self.snapshot.return_value = [{"appId": "sidee_tv",
                                       "url": self._expected_url()}]
        self.dashboard._ensure_sidee_tv_tile_once()
        self.add_tile.assert_not_called()
        self.assertEqual(self.dashboard.tile_status["state"], "up_to_date")

    def test_reinstalls_when_tile_points_elsewhere(self):
        self.snapshot.return_value = [{"appId": "sidee_tv",
                                       "url": "https://example.com/old"}]
        self.dashboard._ensure_sidee_tv_tile_once()
        self.add_tile.assert_called_once_with(
            self.session, "sidee_tv", "Sidee TV", self._expected_url(), "")
        self.assertEqual(self.dashboard.tile_status["state"], "installed")

    def test_skips_without_pairing(self):
        self.load_mock.side_effect = webui.client.AuthError("gone",
                                                            "no session")
        self.dashboard._ensure_sidee_tv_tile_once()
        self.snapshot.assert_not_called()
        self.add_tile.assert_not_called()
        self.assertEqual(self.dashboard.tile_status["state"], "no_pairing")

    def test_skips_when_tv_unreachable(self):
        self.snapshot.side_effect = OSError("no route")
        self.dashboard._ensure_sidee_tv_tile_once()
        self.add_tile.assert_not_called()
        self.assertEqual(self.dashboard.tile_status["state"],
                         "tv_unreachable")

    def test_skips_when_applist_unanswered(self):
        # A timeout is NOT an empty list: installing on an unknown state
        # risks duplicating a tile the TV already has but did not report.
        self.snapshot.return_value = None
        self.dashboard._ensure_sidee_tv_tile_once()
        self.add_tile.assert_not_called()
        self.assertEqual(self.dashboard.tile_status["state"],
                         "tv_unreachable")


if __name__ == "__main__":
    unittest.main()
