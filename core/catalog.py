"""App catalogue: built-in presets + user custom apps, as one list.

The dashboard grid renders this catalogue. Built-in apps come from
``core/presets.py`` and are never modified by the user. Custom apps
are user data, stored as JSON in the user profile (alongside the
TV session), never in the shipped catalogue and never uploaded
anywhere.

Catalogue records (internal form) carry:
    key, app_id, name, url, image, icon, description, category,
    needs_server, server_builder, server_placeholder, source
where ``source`` is "built-in" or "custom" and ``category`` is one
of CATEGORIES. API records add ``installed`` (True/False/None) and
``installed_url``; ``installed`` is None when there is no saved
pairing or the TV did not answer, never a guess.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import tempfile

from . import presets, platform_support

CATEGORIES = ("Media", "Music", "Tools", "Custom")
CUSTOM_FILE = "custom_apps.json"

_last_custom_error: str | None = None


def last_custom_error() -> str | None:
    return _last_custom_error


def custom_apps_path() -> str:
    return os.path.join(str(platform_support.profile_dir()), CUSTOM_FILE)


def _presets_local_path() -> str:
    root = platform_support.resource_root(__file__)
    return os.path.join(str(root), "core", "presets_local.py")


def _clean_record(record: dict) -> dict:
    return {
        "key": record["key"],
        "app_id": record["app_id"],
        "name": record["name"],
        "url": record.get("url", ""),
        "image": record.get("image", ""),
        "icon": record.get("icon", ""),
        "description": record.get("description", ""),
        "category": record.get("category", "Custom"),
        "needs_server": bool(record.get("needs_server", False)),
        "server_builder": record.get("server_builder") or "",
        "server_placeholder": record.get("server_placeholder", ""),
        "source": record.get("source", "custom"),
    }


def built_in_apps() -> list[dict]:
    apps = []
    for key, p in presets.PRESETS.items():
        apps.append(_clean_record({
            "key": key,
            "app_id": p["app_id"],
            "name": p["name"],
            "url": p.get("url", ""),
            "image": p.get("image", ""),
            "icon": p.get("icon", ""),
            "description": p.get("description", ""),
            "category": "Media",
            "needs_server": bool(p.get("needs_server", False)),
            "server_builder": p.get("server_builder", ""),
            "server_placeholder": p.get("server_placeholder", ""),
            "source": "built-in",
        }))
    return apps


def load_custom_apps() -> dict[str, dict]:
    """Custom apps by app_id (lowercase). A missing file is empty;
    a corrupt file is ignored (and reported via last_custom_error)
    so a bad custom file can never break the grid."""
    global _last_custom_error
    _last_custom_error = None
    path = custom_apps_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("custom apps file must contain a list")
        apps = {}
        for item in data:
            cleaned = validate_custom_app(item, allow_existing=True)
            apps[cleaned["app_id"].lower()] = cleaned
        return apps
    except (OSError, ValueError, TypeError) as error:
        _last_custom_error = f"Custom apps could not be loaded: {error}"
        return {}


def _save_custom_apps(apps: dict[str, dict]) -> None:
    path = custom_apps_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=os.path.dirname(path),
                                         delete=False) as f:
            pending = f.name
            json.dump(sorted(apps.values(), key=lambda a: a["name"].lower()),
                      f, indent=1)
        try:
            os.chmod(pending, 0o600)
        except OSError:
            pass
        os.replace(pending, path)
    finally:
        if pending and os.path.isfile(pending):
            os.remove(pending)


def validate_custom_app(data: object, allow_existing: bool = False) -> dict:
    """Validate a custom-app record and return its cleaned form.

    The same rules as the dashboard's preset validation: app IDs
    and names are restricted, tile URLs are https (or http only on
    the private LAN), and icons are https. ``allow_existing`` only
    affects the caller-side collision check, not validation itself.
    """
    if not isinstance(data, dict):
        raise ValueError("custom app must be an object")
    app_id = str(data.get("app_id", "")).strip()
    name = str(data.get("name", "")).strip()
    url = str(data.get("url", "")).strip()
    image = str(data.get("image", "")).strip()
    description = str(data.get("description", "")).strip()
    category = str(data.get("category", "")).strip() or "Custom"
    if not re.fullmatch(r"[a-z0-9_]{1,32}", app_id):
        raise ValueError("app id must use lowercase letters, digits or _ (max 32)")
    if not re.fullmatch(r"[\w \-']{1,40}", name):
        raise ValueError("app name is invalid (max 40 characters)")
    if len(url) > 300 or len(image) > 300 or len(description) > 200:
        raise ValueError("custom app text is too long")
    if url.startswith("https://"):
        pass
    elif url.startswith("http://") and presets.is_private_host(url):
        pass
    else:
        raise ValueError("URL must use https (or http on your LAN)")
    if image and not image.startswith("https://"):
        raise ValueError("icon URL must use https")
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of: {', '.join(CATEGORIES)}")
    return _clean_record({
        "key": app_id,
        "app_id": app_id,
        "name": name,
        "url": url,
        "image": image,
        "icon": "",
        "description": description,
        "category": category,
        "needs_server": False,
        "server_builder": "",
        "server_placeholder": "",
        "source": "custom",
    })


def add_custom_app(data: object) -> dict:
    cleaned = validate_custom_app(data)
    key = cleaned["app_id"].lower()
    if any(a["app_id"].lower() == key or a["key"].lower() == key
           for a in built_in_apps()):
        raise ValueError("that app id is already used by a built-in app")
    apps = load_custom_apps()
    if key in apps:
        raise ValueError("a custom app with that app id already exists")
    apps[key] = cleaned
    _save_custom_apps(apps)
    return cleaned


def remove_custom_app(app_id: str) -> None:
    key = str(app_id or "").strip().lower()
    if any(a["app_id"].lower() == key or a["key"].lower() == key
           for a in built_in_apps()):
        raise ValueError("built-in apps cannot be removed")
    apps = load_custom_apps()
    if key not in apps:
        raise ValueError("custom app not found")
    del apps[key]
    _save_custom_apps(apps)


def get_app(key: str) -> dict | None:
    """Find an app by catalogue key or by app_id (case-insensitive)."""
    wanted = str(key or "").strip().lower()
    if not wanted:
        return None
    for app in built_in_apps():
        if app["key"].lower() == wanted or app["app_id"].lower() == wanted:
            return app
    for app in load_custom_apps().values():
        if app["key"].lower() == wanted or app["app_id"].lower() == wanted:
            return app
    return None


def list_apps() -> list[dict]:
    """Built-ins (in preset order) followed by custom apps (by name)."""
    customs = sorted(load_custom_apps().values(),
                     key=lambda a: a["name"].lower())
    return built_in_apps() + customs


def migrate_presets_local(path: str | None = None) -> int:
    """Import a legacy ``core/presets_local.py`` PRESETS dict as custom
    apps, once. Returns how many apps were imported. This is a
    best-effort migration for users who hand-edited that local file:
    it never overwrites a built-in or an existing custom app, and a
    file that cannot be loaded is simply skipped (the caller may
    report it, but the grid must not fail because of it).

    The file is the user's own local file; it is loaded as a module
    only when it exists, and only by this explicit migration step.
    """
    target = path or _presets_local_path()
    if not os.path.isfile(target):
        return 0
    try:
        spec = importlib.util.spec_from_file_location("sidee_presets_local", target)
        if spec is None or spec.loader is None:
            return 0
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        raw = getattr(module, "PRESETS", None)
        if not isinstance(raw, dict):
            return 0
    except Exception:
        return 0
    apps = load_custom_apps()
    added = 0
    for _key, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            cleaned = validate_custom_app({
                "app_id": value.get("app_id") or _key,
                "name": value.get("name", ""),
                "url": value.get("url", ""),
                "image": value.get("image", ""),
                "description": value.get("description", ""),
                "category": value.get("category", "Custom"),
            })
        except ValueError:
            continue
        key = cleaned["app_id"].lower()
        if any(a["app_id"].lower() == key or a["key"].lower() == key
               for a in built_in_apps()):
            continue
        if key in apps:
            continue
        apps[key] = cleaned
        added += 1
    if added:
        _save_custom_apps(apps)
    return added


def maybe_migrate_presets_local() -> int:
    """Run the legacy migration only when no custom-apps file exists
    yet, so it never re-imports on every catalogue load."""
    if os.path.isfile(custom_apps_path()):
        return 0
    try:
        return migrate_presets_local()
    except Exception:
        return 0


def resolve_url(app: dict, server: str | None) -> str:
    """Build an app's tile URL, as the CLI does for presets.

    Jellyfin-style apps require a server address; Stremio-style apps
    optionally take one. Anything else returns its fixed URL, and a
    missing or invalid server raises ValueError instead of ever
    sending an empty placeholder URL to the TV."""
    if app.get("needs_server"):
        if not server:
            raise ValueError(f"{app['name']} requires your server address: "
                             f"--server YOUR_SERVER_IP:8096")
        return presets.build_server_url(server)
    if app.get("server_builder") == "stremio":
        return presets.build_stremio_url(server or "")
    return app.get("url", "")


def attach_installed(apps: list[dict], tiles: list | None) -> list[dict]:
    """Attach installed state from a TV app list to catalogue records.

    ``tiles`` is the list returned by ``client.list_tiles`` (or None
    when the TV did not answer). Installed means a tile with the same
    app_id is present; the reported URL is attached when available.
    """
    by_id: dict[str, dict] = {}
    if tiles:
        for tile in tiles:
            if isinstance(tile, dict):
                by_id[str(tile.get("appId", "")).lower()] = tile
    out = []
    for app in apps:
        record = dict(app)
        tile = by_id.get(app["app_id"].lower())
        if tiles is None:
            record["installed"] = None
            record["installed_url"] = ""
        elif tile is None:
            record["installed"] = False
            record["installed_url"] = ""
        else:
            record["installed"] = True
            record["installed_url"] = next(
                (str(tile[k]).strip() for k in ("url", "appUrl", "URL")
                 if isinstance(tile.get(k), str) and tile[k].strip()),
                "")
        out.append(record)
    return out
