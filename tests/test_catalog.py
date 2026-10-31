"""Phase 1 grid catalogue: built-ins, custom apps, migration,
installed state, and the dashboard APIs that serve the grid."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import catalog, client, platform_support, webui


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = patch.object(platform_support, "profile_dir",
                               return_value=Path(self.directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        webui._invalidate_catalog_cache()

    def test_built_in_dashboard_icons_are_bundled(self):
        # Phase 4 icon bundling: every built-in's dashboard card icon must
        # be a file in assets/ (never a remote URL), and no built-in may
        # point at the upstream fork.
        import os
        from core import presets
        root = os.path.join(os.path.dirname(__file__), "..")
        for key, preset in presets.PRESETS.items():
            self.assertNotIn("Empi9245", preset.get("image", ""),
                             f"{key} still points at upstream")
            icon = preset.get("icon", "")
            self.assertTrue(icon.startswith("assets/"),
                            f"{key} has no bundled dashboard icon")
            self.assertTrue(os.path.isfile(os.path.join(root, icon)),
                            f"{key} icon missing: {icon}")

    def test_built_ins(self):
        apps = catalog.built_in_apps()
        self.assertEqual([a["key"] for a in apps],
                         ["nuvio", "stremio", "jellyfin",
                          "everythingmoe", "wotaku", "theindex",
                          "justindex", "miruro", "animepahe", "mkissa",
                          "anikototv", "reanime", "animex", "anipm",
                          "nekowatch", "anidap", "anistream", "movy",
                          "cinejoy", "popcornmovies", "flystream",
                          "rivestream", "sevenmovies"])
        self.assertTrue(all(a["category"] == "Media" for a in apps))
        jellyfin = catalog.get_app("jellyfin")
        self.assertTrue(jellyfin["needs_server"])
        self.assertEqual(catalog.get_app("nuviodebug")["key"], "nuvio")
        self.assertEqual(catalog.get_app("NUvio")["key"], "nuvio")
        self.assertIsNone(catalog.get_app("nope"))

    def test_add_custom_persists_and_sorts(self):
        catalog.add_custom_app({"app_id": "zeta", "name": "Zeta",
                                "url": "https://example.com/z"})
        catalog.add_custom_app({"app_id": "alpha", "name": "Alpha",
                                "url": "https://example.com/a",
                                "category": "Tools"})
        path = catalog.custom_apps_path()
        # Windows chmod cannot enforce owner-only permissions (it
        # reports 0o666), so the mode check is Unix-only, matching
        # test_platform_support's certificate-file check.
        if os.name != "nt":
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        customs = catalog.list_apps()[len(catalog.built_in_apps()):]
        self.assertEqual([a["key"] for a in customs], ["alpha", "zeta"])
        self.assertEqual(customs[1]["source"], "custom")

    def test_add_custom_collisions(self):
        for app_id in ("nuvio", "jellyfin", "nuviodebug"):
            with self.assertRaises(ValueError):
                catalog.add_custom_app({"app_id": app_id, "name": "X",
                                        "url": "https://example.com/x"})
        catalog.add_custom_app({"app_id": "myapp", "name": "My App",
                                "url": "https://example.com/app"})
        with self.assertRaises(ValueError):
            catalog.add_custom_app({"app_id": "myapp", "name": "Again",
                                    "url": "https://example.com/other"})

    def test_validate_custom_rejects_bad_input(self):
        bad = [
            {"app_id": "MyApp", "name": "X", "url": "https://example.com"},
            {"app_id": "ok", "name": "X", "url": "http://example.com"},
            {"app_id": "ok", "name": "X", "url": "https://example.com",
             "image": "http://example.com/icon.png"},
            {"app_id": "ok", "name": "X", "url": "https://example.com",
             "category": "Games"},
            {"app_id": "ok", "name": "X" * 41, "url": "https://example.com"},
            {"app_id": "ok", "name": "X", "url": ""},
        ]
        for data in bad:
            with self.assertRaises(ValueError, msg=str(data)):
                catalog.validate_custom_app(data)
        # LAN http is allowed, as for presets.
        cleaned = catalog.validate_custom_app(
            {"app_id": "lanapp", "name": "LAN App",
             "url": "http://192.168.1.10:8080/app"})
        self.assertEqual(cleaned["url"], "http://192.168.1.10:8080/app")

    def test_remove_custom(self):
        catalog.add_custom_app({"app_id": "myapp", "name": "My App",
                                "url": "https://example.com/app"})
        catalog.remove_custom_app("myapp")
        self.assertIsNone(catalog.get_app("myapp"))
        with self.assertRaises(ValueError):
            catalog.remove_custom_app("nuvio")
        with self.assertRaises(ValueError):
            catalog.remove_custom_app("missing")

    def test_resolve_url_never_returns_empty_for_server_apps(self):
        jellyfin = catalog.get_app("jellyfin")
        with self.assertRaises(ValueError):
            catalog.resolve_url(jellyfin, None)
        url = catalog.resolve_url(jellyfin, "192.168.1.10:8096")
        self.assertIn("192.168.1.10", url)
        stremio = catalog.get_app("stremio")
        self.assertTrue(catalog.resolve_url(stremio, None).startswith("https://"))
        self.assertIn("192.168.1.10",
                      catalog.resolve_url(stremio, "http://192.168.1.10:11470"))
        self.assertTrue(catalog.resolve_url(catalog.get_app("nuvio"), None))

    def test_attach_installed(self):
        apps = catalog.list_apps()
        self.assertTrue(all(a["installed"] is None
                            for a in catalog.attach_installed(apps, None)))
        attached = catalog.attach_installed(
            apps, [{"appId": "nuviodebug", "url": "https://example.com/tile"}])
        by_key = {a["key"]: a for a in attached}
        self.assertTrue(by_key["nuvio"]["installed"])
        self.assertEqual(by_key["nuvio"]["installed_url"],
                         "https://example.com/tile")
        self.assertFalse(by_key["stremio"]["installed"])

    def test_migrate_presets_local(self):
        legacy = Path(self.directory.name) / "presets_local.py"
        legacy.write_text(
            "PRESETS = {\n"
            "    'oldapp': {'app_id': 'oldapp', 'name': 'Old App',\n"
            "                 'url': 'https://example.com/old', 'image': '',\n"
            "                 'description': 'Legacy'},\n"
            "    'nuvio': {'app_id': 'nuvio', 'name': 'Fake',\n"
            "                'url': 'https://example.com/fake'},\n"
            "    'broken': {'app_id': 'broken', 'name': 'Broken', 'url': ''},\n"
            "}\n", encoding="utf-8")
        self.assertEqual(catalog.migrate_presets_local(str(legacy)), 1)
        self.assertEqual(catalog.get_app("oldapp")["name"], "Old App")
        self.assertEqual(catalog.get_app("nuvio")["name"], "Nuvio")
        # Once the custom file exists, migration does not re-run.
        self.assertEqual(catalog.maybe_migrate_presets_local(), 0)


class WebuiCatalogTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = patch.object(platform_support, "profile_dir",
                               return_value=Path(self.directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        webui._invalidate_catalog_cache()

    def test_catalog_unpaired(self):
        with patch.object(client.Session, "load_or_none",
                          return_value=None):
            data = webui._catalog_data()
        self.assertTrue(data["ok"])
        self.assertFalse(data["paired"])
        self.assertEqual(len(data["apps"]), len(catalog.built_in_apps()))
        self.assertTrue(all(a["installed"] is None for a in data["apps"]))

    def test_catalog_paired_caches_and_forces_refresh(self):
        session = Mock()
        session.host = "192.168.1.50"
        tiles = [{"appId": "nuviodebug", "url": "https://example.com/t"}]
        with patch.object(client.Session, "load_or_none",
                          return_value=session), \
                patch.object(client, "list_tiles",
                             return_value=tiles) as list_tiles:
            first = webui._catalog_data()
            second = webui._catalog_data()
            third = webui._catalog_data(force_refresh=True)
        self.assertTrue(first["apps"][0]["installed"])
        self.assertFalse(first["apps"][1]["installed"])
        self.assertTrue(second["cached"])
        self.assertFalse(third["cached"])
        self.assertEqual(list_tiles.call_count, 2)

    def test_catalog_tv_failure_returns_unknown_not_error(self):
        session = Mock()
        session.host = "192.168.1.50"
        with patch.object(client.Session, "load_or_none",
                          return_value=session), \
                patch.object(client, "list_tiles",
                             side_effect=ConnectionError("TV did not answer")):
            data = webui._catalog_data()
        self.assertTrue(data["ok"])
        self.assertTrue(all(a["installed"] is None for a in data["apps"]))
        self.assertIn("tv_error", data)

    def test_launch_app(self):
        catalog.add_custom_app({"app_id": "myapp", "name": "My App",
                                "url": "https://example.com/app"})
        session = Mock()
        with patch.object(client.Session, "load", return_value=session), \
                patch.object(client, "launch_tile") as launch:
            self.assertFalse(webui._launch_app({"app": "jellyfin"})["ok"])
            result = webui._launch_app({"app": "jellyfin",
                                        "server": "192.168.1.10:8096"})
            self.assertTrue(result["ok"])
            launch.assert_called_once()
            self.assertIn("192.168.1.10", launch.call_args[0][3])
            self.assertFalse(webui._launch_app({"app": "missing"})["ok"])
            self.assertTrue(webui._launch_app({"app": "myapp"})["ok"])

    def test_custom_api_add_remove(self):
        self.assertTrue(webui._add_custom(
            {"app_id": "myapp", "name": "My App",
             "url": "https://example.com/app"})["ok"])
        self.assertFalse(webui._add_custom(
            {"app_id": "myapp", "name": "Dup",
             "url": "https://example.com/other"})["ok"])
        self.assertTrue(webui._remove_custom({"app_id": "myapp"})["ok"])
        self.assertFalse(webui._remove_custom({"app_id": "myapp"})["ok"])

    def test_install_custom_via_catalog(self):
        catalog.add_custom_app({"app_id": "myapp", "name": "My App",
                                "url": "https://example.com/app"})
        handler = webui.Handler.__new__(webui.Handler)
        session = Mock()
        with patch.object(client.Session, "load", return_value=session), \
                patch.object(client, "add_tile",
                             return_value=[{"appId": "myapp",
                                            "url": "https://example.com/app"}]):
            result = handler._install({"app": "myapp"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "installed")
        self.assertFalse(handler._install({"app": "jellyfin"})["ok"])

    def test_diagnostics_unpaired_and_paired(self):
        with patch.object(webui, "_local_interfaces",
                          return_value=[("eth0", "192.168.1.2")]), \
                patch.object(client.Session, "load_or_none",
                             return_value=None):
            data = webui._diagnostics()
        self.assertFalse(data["ok"])
        self.assertEqual(data["steps"][0]["ok"], True)
        self.assertIsNone(data["steps"][2]["ok"])
        self.assertNotIn("token", json.dumps(data))
        session = Mock()
        session.host = "192.168.1.50"
        with patch.object(client.Session, "load_or_none",
                          return_value=session), \
                patch.object(webui, "_probe_tv_ip",
                             return_value={"ok": True,
                                           "message": "VIDAA TV verified"}):
            data = webui._diagnostics()
        self.assertTrue(data["ok"])
        self.assertTrue(data["steps"][2]["ok"])


if __name__ == "__main__":
    unittest.main()
