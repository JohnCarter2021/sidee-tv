"""Real local HTTP lifecycle and launcher regression checks; no TV access."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from core import webui
import macos_launcher
import sidee
from tools.smoke_test import request, smoke


class TestDashboardLifecycle(unittest.TestCase):
    def test_error_messages_use_plain_language(self):
        from unittest.mock import Mock
        from core import client
        expired = Mock(host="192.168.1.10", expires_at=1)
        with patch.object(client.Session, "load_or_none", return_value=expired):
            status = webui._status()
        self.assertEqual(status["state"], "expired")
        self.assertNotIn("Token", status["message"])
        self.assertIn("pair again", status["message"])
        with patch.object(client.Session, "load_or_none", return_value=None):
            status = webui._status()
        self.assertEqual(status["state"], "needs_pairing")
        self.assertIn("PIN shown on your TV", status["message"])
        page = (Path(__file__).resolve().parent.parent
                / "core" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("same Wi-Fi", page)

    def test_discover_failure_hides_raw_exceptions(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"SIDEE_STATE_DIR": directory}), \
                patch.object(webui.client, "discover",
                             side_effect=OSError("network unreachable")):
            dashboard = webui.Dashboard(port=0)
            try:
                dashboard.start()
                status, _, body = request(dashboard.port, "/api/discover?key=" +
                                          webui.ACCESS_KEY)
                self.assertEqual(status, 200)
                payload = json.loads(body)
                self.assertFalse(payload["ok"])
                self.assertNotIn("OSError", payload["error"])
                self.assertIn("Wi-Fi", payload["error"])
            finally:
                dashboard.close()

    def test_forget_tv_deletes_saved_pairing(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"SIDEE_STATE_DIR": directory}):
            from core import client
            path = Path(client.Session.path())
            path.write_text("{}")
            dashboard = webui.Dashboard(port=0)
            try:
                dashboard.start()
                status, _, body = request(dashboard.port, "/api/forget?key=" +
                                          webui.ACCESS_KEY, "POST", "{}")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), {"ok": True, "forgotten": True})
                self.assertFalse(path.exists())
                status, _, body = request(dashboard.port, "/api/forget?key=" +
                                          webui.ACCESS_KEY, "POST", "{}")
                self.assertEqual(json.loads(body), {"ok": True, "forgotten": False})
            finally:
                dashboard.close()

    def test_loopback_bind_is_used_when_requested(self):
        # Regression: Android's sidee_android passes host="127.0.0.1"
        # and run #20 crashed with "unexpected keyword argument 'host'"
        # because Dashboard did not accept it at all.
        dashboard = webui.Dashboard(port=0, headless=True, host="127.0.0.1")
        try:
            self.assertEqual(dashboard.server.server_address[0], "127.0.0.1")
        finally:
            dashboard.server.server_close()

    def test_default_bind_is_still_all_interfaces(self):
        dashboard = webui.Dashboard(port=0)
        try:
            self.assertEqual(dashboard.server.server_address[0], "0.0.0.0")
        finally:
            dashboard.server.server_close()

    def test_startup_does_not_wait_for_hostname_dns(self):
        with patch("socket.getfqdn", side_effect=AssertionError("reverse DNS used")):
            dashboard = webui.Dashboard(port=0)
            self.assertEqual(dashboard.server.server_name, "localhost")
            dashboard.server.server_close()

    def test_headless_real_process_startup_and_shutdown(self):
        import sys
        root = Path(__file__).resolve().parent.parent
        smoke([sys.executable, str(root / "sidee.py")])

    def test_gui_server_has_no_remote_shutdown_endpoint(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"SIDEE_STATE_DIR": directory}):
            dashboard = webui.Dashboard(port=0)
            try:
                dashboard.start()
                status, _, body = request(dashboard.port, "/api/shutdown?key=" +
                                         webui.ACCESS_KEY, "POST", "{}")
                self.assertEqual(status, 404)
                self.assertFalse(dashboard.stop_event.is_set())
                self.assertEqual(json.loads(body), {"error": "not found"})
            finally:
                dashboard.close()
            self.assertFalse((Path(directory) / "runtime" / "dashboard.json").exists())

    def test_failed_state_write_closes_bound_socket(self):
        dashboard = webui.Dashboard(port=0)
        port = dashboard.port
        with patch.object(webui, "_remember_dashboard", side_effect=OSError("read only")), \
                patch.object(webui, "_forget_dashboard"):
            with self.assertRaises(OSError):
                dashboard.start()
        import socket
        with socket.socket() as probe:
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)

    def test_headless_cli_never_opens_browser(self):
        with patch("sys.argv", ["sidee.py", "--headless", "--port", "0"]), \
                patch.object(webui, "serve") as serve:
            self.assertEqual(sidee.main(), 0)
        serve.assert_called_once_with(open_browser=False, port=0, headless=True)

    def test_ci_environment_disables_gui_and_browser(self):
        with patch("sys.argv", ["Sidee"]), \
                patch.dict(os.environ, {"SIDEE_CI": "1"}), \
                patch.object(macos_launcher, "run_gui") as gui, \
                patch.object(webui, "serve") as serve:
            self.assertEqual(macos_launcher.main(), 0)
        gui.assert_not_called()
        serve.assert_called_once_with(open_browser=False, port=None, headless=True)

    def test_headless_failure_never_opens_an_error_dialog(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("sys.argv", ["Sidee", "--self-test"]), \
                patch.dict(os.environ, {"SIDEE_STATE_DIR": directory}), \
                patch.object(sidee, "main", side_effect=OSError("startup fixture")), \
                patch.object(macos_launcher, "run_gui") as gui, \
                patch.object(macos_launcher, "_fallback_error") as dialog:
            self.assertEqual(macos_launcher.main(), 1)
            self.assertIn("startup fixture", (Path(directory) / "logs" / "sidee.log").read_text())
        gui.assert_not_called()
        dialog.assert_not_called()

    def test_pending_pairing_wakes_on_application_close(self):
        from core.pairing import PairingFlow
        flow = PairingFlow()
        attempt = flow.attempt = Mock()
        flow.close()
        attempt.cancel.assert_called_once_with()
        attempt.done.wait.assert_called_once_with(timeout=1)


if __name__ == "__main__":
    unittest.main()
