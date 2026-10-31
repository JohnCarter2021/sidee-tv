"""Android /tv/ access guard: the Android entry point must bind the
dashboard to all interfaces, or a TV browser on the LAN cannot reach
/tv/ (the original loopback bind made the app phone-only).

Parsed from source, not imported: the module lives under android/,
outside the testable core tree, and importing it would start
Chaquopy-only machinery.
"""
import ast
import unittest
from pathlib import Path

ENTRY = Path(__file__).resolve().parent.parent / "android" / "app" / \
    "src" / "main" / "python" / "sidee_android.py"


def dashboard_host_kwargs(tree: ast.AST) -> list:
    hosts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name == "Dashboard":
                for kw in node.keywords:
                    if kw.arg == "host" and isinstance(kw.value, ast.Constant):
                        hosts.append(kw.value.value)
    return hosts


class TestAndroidTvAccess(unittest.TestCase):
    def test_dashboard_binds_all_interfaces(self):
        tree = ast.parse(ENTRY.read_text())
        hosts = dashboard_host_kwargs(tree)
        self.assertEqual(hosts, ["0.0.0.0"])

    def test_entry_does_not_pin_a_random_port(self):
        # The dashboard must prefer its saved port (then 8787) so the
        # Sidee TV tile's address survives app restarts; pinning port=0
        # gave every launch a new address and left the tile stale until
        # the auto-tile thread reinstalled it.
        tree = ast.parse(ENTRY.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                if name == "Dashboard":
                    for kw in node.keywords:
                        if kw.arg == "port":
                            self.assertFalse(
                                isinstance(kw.value, ast.Constant)
                                and kw.value.value == 0,
                                "Dashboard must not pin port=0")

    def test_entry_still_returns_loopback_url_for_webview(self):
        # Dashboard.url is loopback by construction (see core/webui.py);
        # the entry must keep returning it for the in-app WebView.
        text = ENTRY.read_text()
        self.assertIn("return _dashboard.url", text)


if __name__ == "__main__":
    unittest.main()
