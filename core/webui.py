"""Local Sidee web interface: three steps — find TV -> enter
the PIN displayed on the TV -> click the app to install.

Security: the dashboard is accessible only with the unique key printed
at startup (in the URL and QR code); installation URLs must use
https; the PIN and tokens are never logged."""
from __future__ import annotations

import http.server
import http.client
import ipaddress
import json
import os
import re
import secrets
import signal
import socket
import socketserver
import tempfile
import threading
import time
import urllib.parse
import webbrowser

from . import catalog, client, presets, platform_support, tv_frontend, update_check
from .pairing import PairingFlow
from .phone import qr_image

_PORT = 8787
ROOT = str(platform_support.resource_root(__file__))
ACCESS_KEY = secrets.token_urlsafe(16)
PAIRING = PairingFlow()
# Enter your Ko-fi/Sponsors link here: it appears in the dashboard footer
KOFI_URL = "https://ko-fi.com/sidee"

with open(os.path.join(ROOT, "core", "dashboard.html"), encoding="utf-8") as _page_file:
    _PAGE = _page_file.read()


def _status() -> dict:
    s = client.Session().load_or_none()
    if not s:
        return {"paired": False, "state": "needs_pairing",
                "message": "Pair your TV first: enter the PIN shown on your TV."}
    if s.expires_at and time.time() >= s.expires_at:
        return {"paired": True, "state": "expired", "host": s.host,
                "expires_at": s.expires_at,
                "message": "Your TV connection has expired. Request a new code "
                "on your TV and pair again."}
    return {"paired": True, "state": "ok", "host": s.host,
            "expires_at": s.expires_at}


def _phone_access(port: int, tv_host: str | None = None) -> dict:
    host = _local_ip(tv_host)
    address = ipaddress.IPv4Address(host)
    if (address.is_loopback or address.is_unspecified or address.is_multicast
            or address.is_link_local):
        return {"ok": False, "error": "Connect this computer to your home network, "
                "then refresh this page to get the phone QR code."}
    url = f"http://{host}:{port}/?key={ACCESS_KEY}"
    return {"ok": True, "url": url, "qr": qr_image(url)}


def _probe_tv_ip(host: str) -> dict:
    """Verify a manually entered LAN IPv4 before allowing PIN pairing."""
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        return {"ok": False, "error": "Enter a valid TV IPv4 address, e.g. 192.168.1.50."}
    # Do not probe Internet, loopback, link-local or multicast addresses.
    subnets = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    if not any(address in ipaddress.IPv4Network(net) for net in subnets):
        return {"ok": False, "error": "Use a private IPv4 address on your home network."}
    info = client.fetch_descriptor(str(address))
    try:
        with socket.create_connection((str(address), client.MQTT_PORT), timeout=2):
            mqtt_open = True
    except OSError:
        mqtt_open = False
    if not info or not info.is_vidaa:
        message = ("Port 36669 responds, but Sidee could not verify a VIDAA TV "
                   "using its device description." if mqtt_open else
                   "No VIDAA TV description or port 36669 response at that IP. "
                   "Check the TV address, its network and VPN settings.")
        return {"ok": False, "error": message}
    if not mqtt_open:
        return {"ok": False, "error": "VIDAA TV found, but TCP port 36669 is "
                "unreachable. Check local network permissions, VPN, firewall "
                "and Wi-Fi isolation."}
    return {"ok": True, "tv": {**info.__dict__, "raw_description": ""},
            "message": "VIDAA TV verified by IP. Automatic SSDP discovery may "
                       "be blocked; PIN pairing is still required."}


_CATALOG_CACHE: dict = {"apps": None, "at": 0.0, "host": None}
_CATALOG_LOCK = threading.Lock()
_CATALOG_TTL = 60.0


def _invalidate_catalog_cache() -> None:
    with _CATALOG_LOCK:
        _CATALOG_CACHE["apps"] = None
        _CATALOG_CACHE["at"] = 0.0
        _CATALOG_CACHE["host"] = None


def _catalog_data(force_refresh: bool = False) -> dict:
    """Catalogue for the grid, with cached installed state.

    The grid must render instantly: a fresh TV app-list request
    takes seconds, so a recent result is reused (60 s) and the
    caller can force a refresh. If the TV does not answer, the
    apps are still returned with installed=None, never guessed,
    and a cached result is preferred over an error."""
    catalog.maybe_migrate_presets_local()
    apps = catalog.list_apps()
    custom_error = catalog.last_custom_error()
    session = client.Session().load_or_none()
    if not session:
        return {"ok": True, "apps": catalog.attach_installed(apps, None),
                "cached": False, "refreshed_at": None, "paired": False,
                "custom_error": custom_error}
    with _CATALOG_LOCK:
        cached = _CATALOG_CACHE["apps"]
        age = time.time() - _CATALOG_CACHE["at"]
        if (cached is not None and _CATALOG_CACHE["host"] == session.host
                and not force_refresh and age < _CATALOG_TTL):
            return {"ok": True, "apps": cached, "cached": True,
                    "refreshed_at": int(_CATALOG_CACHE["at"]),
                    "paired": True, "custom_error": custom_error}
    try:
        tiles = client.list_tiles(session)
    except Exception as e:
        with _CATALOG_LOCK:
            if (_CATALOG_CACHE["apps"] is not None
                    and _CATALOG_CACHE["host"] == session.host):
                return {"ok": True, "apps": _CATALOG_CACHE["apps"],
                        "cached": True,
                        "refreshed_at": int(_CATALOG_CACHE["at"]),
                        "paired": True, "custom_error": custom_error,
                        "tv_error": str(e)}
        return {"ok": True, "apps": catalog.attach_installed(apps, None),
                "cached": False, "refreshed_at": None, "paired": True,
                "custom_error": custom_error, "tv_error": str(e)}
    attached = catalog.attach_installed(apps, tiles)
    with _CATALOG_LOCK:
        _CATALOG_CACHE["apps"] = attached
        _CATALOG_CACHE["at"] = time.time()
        _CATALOG_CACHE["host"] = session.host
    return {"ok": True, "apps": attached, "cached": False,
            "refreshed_at": int(_CATALOG_CACHE["at"]), "paired": True,
            "custom_error": custom_error}


def _launch_app(data: dict) -> dict:
    app = catalog.get_app(str(data.get("app", "")))
    if not app:
        return {"ok": False, "error": "unknown app"}
    server = str(data.get("server", "")).strip()
    try:
        url = catalog.resolve_url(app, server or None)
        _validate_preset({"app_id": app["app_id"], "url": url,
                          "name": app["name"], "image": app["image"]})
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    session = client.Session.load()
    client.launch_tile(session, app["app_id"], app["name"], url)
    return {"ok": True, "name": app["name"]}


def _add_custom(data: dict) -> dict:
    try:
        cleaned = catalog.add_custom_app(data)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    _invalidate_catalog_cache()
    return {"ok": True, "app": cleaned}


def _remove_custom(data: dict) -> dict:
    try:
        catalog.remove_custom_app(str(data.get("app_id", "")))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    _invalidate_catalog_cache()
    return {"ok": True}


def _local_interfaces() -> list:
    """Local IPv4 interfaces, with an `ip addr` fallback on Linux.

    platform_support.local_ipv4_interfaces() now handles Linux
    (`ip addr`, then `ifconfig`); this fallback only runs if it
    still returns nothing, so diagnostics never report a false
    "no network" from a single failed probe. The fallback parses
    only `ip addr` output for non-loopback inet addresses."""
    try:
        interfaces = platform_support.local_ipv4_interfaces()
    except Exception:
        interfaces = []
    if interfaces:
        return interfaces
    if platform_support.sys.platform != "linux":
        return interfaces
    try:
        import subprocess
        out = subprocess.run(["ip", "addr"], capture_output=True,
                             text=True, timeout=3).stdout
    except Exception:
        return interfaces
    found = []
    for line in out.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "inet":
            ip = parts[1].split("/")[0]
            if not ip.startswith("127."):
                found.append(("ip", ip))
    return found


def _diagnostics() -> dict:
    """Check-my-setup steps. Never includes tokens, PINs or the
    dashboard key: only step results and the TV host (LAN IP)."""
    steps = []
    try:
        interfaces = _local_interfaces()
    except Exception:
        interfaces = []
    steps.append({"name": "Local network",
                  "ok": bool(interfaces),
                  "detail": (f"{len(interfaces)} local interface(s) found"
                             if interfaces else
                             "No local IPv4 interface found: check your network")})
    session = client.Session().load_or_none()
    steps.append({"name": "Saved pairing",
                  "ok": session is not None,
                  "detail": (f"Paired with TV at {session.host}" if session
                             else "No saved pairing: pair your TV first")})
    if session:
        probe = _probe_tv_ip(session.host)
        steps.append({"name": "TV reachable",
                      "ok": bool(probe.get("ok")),
                      "detail": (probe.get("message") or probe.get("error")
                                 or "TV check failed")})
    else:
        steps.append({"name": "TV reachable", "ok": None,
                      "detail": "Skipped: pair your TV first"})
    steps.append({"name": "Dashboard", "ok": True,
                  "detail": "Dashboard is running on this device"})
    return {"ok": all(s["ok"] for s in steps if s["ok"] is not None),
            "steps": steps, "paired": session is not None}


def _forget_tv() -> dict:
    """Delete the saved TV pairing so another TV can be paired.

    Only the pairing file goes: the dashboard keeps running and
    installed tiles on the TV are untouched (they live on the TV).
    """
    path = client.Session.path()
    forgotten = False
    if os.path.isfile(path):
        os.remove(path)
        forgotten = True
    _invalidate_catalog_cache()
    return {"ok": True, "forgotten": forgotten}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _authorized(self) -> bool:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return q.get("key", [""])[0] == ACCESS_KEY

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Sidee", "2")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, body, ctype, code=200, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            if v is not None:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = urllib.parse.urlparse(self.path)
        path = parts.path
        if not path.startswith("/assets/") and not self._authorized():
            # static assets are public; everything else requires the key
            self._json({"error": "unauthorized"}, 403)
            return
        if path == "/":
            body = _PAGE.replace("KOFI_URL_PLACEHOLDER", KOFI_URL).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path.startswith("/assets/"):
            # allowlist: only PNG files from the assets/ package
            name = os.path.basename(path)
            p = os.path.join(ROOT, "assets", name)
            if not name.endswith(".png") or not os.path.isfile(p):
                self._json({"error": "not found"}, 404)
                return
            body = open(p, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/status":
            self._json(_status())
        elif path == "/api/update":
            self._json(update_check.check())
        elif path == "/api/phone":
            query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
            tv_host = query.get("tv_host", [None])[0]
            if tv_host is not None:
                try:
                    ipaddress.IPv4Address(tv_host)
                except ValueError:
                    self._json({"ok": False, "error": "The TV IP address is invalid. "
                                "Find your TV again to update the phone QR code."})
                    return
            self._json(_phone_access(self.server.server_address[1], tv_host))
        elif path == "/api/catalog":
            query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
            force = query.get("force", [""])[0] == "1"
            self._json(_catalog_data(force_refresh=force))
        elif path == "/api/diagnostics":
            self._json(_diagnostics())
        elif path == "/api/discover":
            try:
                tvs = [t.__dict__ | {"raw_description": ""}
                       for t in client.discover()]
                self._json({"ok": True, "tvs": tvs})
            except Exception:
                self._json({"ok": False, "error": "Couldn't search the network. "
                                "Check this device is on Wi-Fi, then try again."})
        elif path in ("/tv", "/tv/"):
            self._bytes(tv_frontend.menu_page(ACCESS_KEY).encode("utf-8"),
                        "text/html; charset=utf-8")
        elif path == "/tv/page":
            query = urllib.parse.parse_qs(parts.query)
            u = query.get("u", [""])[0]
            code, ctype, body = tv_frontend.page_response(u, ACCESS_KEY)
            self._bytes(body, ctype, code)
        elif path == "/tv/play":
            query = urllib.parse.parse_qs(parts.query)
            watch = query.get("watch", [""])[0]
            code, ctype, body = tv_frontend.play_response(watch, ACCESS_KEY)
            self._bytes(body, ctype, code)
        elif path == "/tv/stream":
            query = urllib.parse.parse_qs(parts.query)
            u = query.get("u", [""])[0]
            code, ctype, crange, body = tv_frontend.stream_response(
                u, self.headers.get("Range"), ACCESS_KEY)
            self._bytes(body, ctype, code,
                        {"Content-Range": crange} if crange else None)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        parts = urllib.parse.urlparse(self.path)
        if not self._authorized():
            self._json({"error": "unauthorized"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 4096:
                self._json({"ok": False, "error": "payload too large"})
                return
            data = json.loads(self.rfile.read(length) or b"{}")
            if parts.path == "/api/pair/start":
                host = str(data.get("host", ""))
                try:
                    ipaddress.IPv4Address(host)
                except ValueError:
                    self._json({"ok": False, "error": "invalid IP address"})
                    return
                self._json(PAIRING.start(host))
            elif parts.path == "/api/pair":
                self._json(PAIRING.confirm(str(data.get("pairing_id", "")),
                                           str(data.get("pin", ""))))
            elif parts.path == "/api/pair/cancel":
                self._json(PAIRING.cancel(str(data.get("pairing_id", ""))))
            elif parts.path == "/api/forget":
                self._json(_forget_tv())
            elif parts.path == "/api/tv/check":
                self._json(_probe_tv_ip(str(data.get("host", "")).strip()))
            elif (parts.path == "/api/shutdown" and
                  getattr(self.server, "headless", False) and
                  ipaddress.ip_address(self.client_address[0]).is_loopback):
                self._json({"ok": True})
                self.server.stop_event.set()
            elif parts.path == "/api/launch":
                try:
                    result = _launch_app(data)
                except client.AuthError as e:
                    self._json({"ok": False, "error": str(e),
                                "needs_pairing": e.kind in
                                ("none", "rejected", "expired", "corrupt", "needs_pairing")})
                    return
                self._json(result)
            elif parts.path == "/api/custom":
                self._json(_add_custom(data))
            elif parts.path == "/api/custom/remove":
                self._json(_remove_custom(data))
            elif parts.path == "/api/install":
                try:
                    result = self._install(data)
                except client.AuthError as e:
                    self._json({"ok": False, "error": str(e),
                                "needs_pairing": e.kind in
                                ("none", "rejected", "expired", "corrupt", "needs_pairing")})
                    return
                self._json(result)
            else:
                self._json({"error": "not found"}, 404)
        except client.AuthError as e:
            self._json({"ok": False, "error": str(e),
                        "needs_pairing": e.kind in
                        ("none", "rejected", "expired", "corrupt", "needs_pairing")})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _install(self, data: dict) -> dict:
        app = catalog.get_app(str(data.get("app", "")))
        if not app:
            return {"ok": False, "error": "unknown app"}
        server = str(data.get("server", "")).strip()
        if app.get("needs_server") and not server:
            return {"ok": False, "error": "enter your " + app["name"]
                                          + " server address"}
        # Invalid server addresses raise ValueError here, as before:
        # the HTTP handler turns that into an error response, and no
        # TV session is loaded or contacted for a bad address.
        session = None
        if app["app_id"] == "sidee_tv":
            # Sidee TV's URL is the live dashboard, not a preset string:
            # the TV must reach this machine's LAN address with this
            # run's access key, so it is built here, never resolved.
            session = client.Session.load()
            host_ip = _local_ip(session.host)
            try:
                address = ipaddress.ip_address(host_ip)
            except ValueError:
                address = None
            if address is None or address.is_loopback \
                    or address.is_unspecified:
                return {"ok": False,
                        "error": "Sidee TV needs this machine on the same "
                                 "Wi-Fi as the TV; no LAN address was found."}
            url = tv_frontend.absolute_tv_url(
                host_ip, self.server.server_address[1], ACCESS_KEY)
        else:
            url = catalog.resolve_url(app, server or None)
        p = {"app_id": app["app_id"], "name": app["name"], "url": url,
             "image": app["image"]}
        _validate_preset(p)
        s = session or client.Session.load()
        apps = client.add_tile(s, p["app_id"], p["name"], p["url"],
                               p["image"])
        _invalidate_catalog_cache()
        found = [a for a in apps
                 if isinstance(a, dict) and
                 str(a.get("appId", "")).lower() == p["app_id"]]
        confirmed = any(client.tile_matches_request(a, p["app_id"], p["url"])
                        for a in found)
        dups = len(found)
        return {"ok": confirmed,
                "status": "installed" if confirmed else "unconfirmed",
                "error": None,
                "message": None if confirmed else
                p["name"] + " installation was requested, but the TV has not "
                "confirmed its current address yet. Check Home on your TV "
                "before trying again.",
                "duplicates": max(0, dups - 1) if found else 0}


def _validate_preset(p: dict) -> None:
    """Tile URLs must use https; http is allowed ONLY for hosts on
    the user's private network (e.g. their own Jellyfin server)."""
    if not re.fullmatch(r"[a-z0-9_]{1,32}", p["app_id"]):
        raise ValueError("invalid app_id")
    url = p["url"]
    if url.startswith("https://") and len(url) <= 300:
        pass
    elif url.startswith("http://") and presets.is_private_host(url) \
            and len(url) <= 300:
        pass
    else:
        raise ValueError("URL must use https (or http on your LAN)")
    if not re.fullmatch(r"[\w \-']{1,40}", p["name"]):
        raise ValueError("invalid name")
    if p["image"] and not p["image"].startswith("https://"):
        raise ValueError("icon URL must use https")


def _dashboard_state_path() -> str:
    return str(platform_support.dashboard_state_path(ROOT))


def _reopen_dashboard(open_browser: bool) -> bool:
    """A second double-click opens this folder's existing dashboard."""
    connection = None
    try:
        with open(_dashboard_state_path(), encoding="utf-8") as f:
            state = json.load(f)
        port, key = state["port"], state["key"]
        if (type(port) is not int or not 0 < port < 65536 or
                not isinstance(key, str) or not key):
            return False
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        connection.request("GET", "/api/status?key=" + urllib.parse.quote(key, safe=""))
        response = connection.getresponse()
        if response.status != 200 or response.getheader("X-Sidee") != "2":
            return False
        response.read()
        url = f"http://127.0.0.1:{port}/?key={urllib.parse.quote(key, safe='')}"
        if open_browser:
            webbrowser.open(url)
        print("Your dashboard is already running. Use its original window to close it.")
        return True
    except (OSError, ValueError, TypeError, KeyError, http.client.HTTPException):
        return False
    finally:
        if connection:
            connection.close()


def _remember_dashboard(port: int) -> None:
    path = _dashboard_state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=os.path.dirname(path), delete=False) as f:
            pending = f.name
            json.dump({"port": port, "key": ACCESS_KEY, "pid": os.getpid()}, f)
        os.chmod(pending, 0o600)
        os.replace(pending, path)
    finally:
        if pending and os.path.isfile(pending):
            os.remove(pending)


def _identity_path() -> str:
    return os.path.join(str(platform_support.profile_dir()),
                        "dashboard_identity.json")


def _load_identity() -> dict:
    """Saved dashboard identity (access key + last port), or {}.

    Kept apart from the runtime state file on purpose: _forget_dashboard
    deletes the runtime file on a clean shutdown, but the identity must
    survive restarts so an installed Sidee TV tile keeps working.
    """
    try:
        with open(_identity_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    key = data.get("key", "")
    port = data.get("port", 0)
    if (not isinstance(key, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{16,}", key)
            or type(port) is not int or not 0 < port < 65536):
        return {}
    return {"key": key, "port": port}


def _save_identity(key: str, port: int) -> None:
    path = _identity_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=os.path.dirname(path),
                                         delete=False) as f:
            pending = f.name
            json.dump({"key": key, "port": port}, f)
        os.chmod(pending, 0o600)
        os.replace(pending, path)
    finally:
        if pending and os.path.isfile(pending):
            os.remove(pending)


def _forget_dashboard() -> None:
    try:
        path = _dashboard_state_path()
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        if state.get("pid") == os.getpid() and state.get("key") == ACCESS_KEY:
            os.remove(path)
    except (OSError, ValueError, AttributeError):
        pass


class DashboardServer(http.server.ThreadingHTTPServer):
    # Windows SO_REUSEADDR can silently share the port with another process.
    # Each dashboard must exclusively own its address and access key.
    allow_reuse_address = platform_support.allow_reuse_address()
    allow_reuse_port = False

    def server_bind(self):
        platform_support.configure_exclusive_tcp_socket(self.socket)
        # HTTPServer's default bind performs reverse DNS for 0.0.0.0. That
        # lookup can stall macOS startup on offline or filtered networks.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


def _bind_dashboard_server(port: int | None = None, host: str = "0.0.0.0",
                           saved_port: int | None = None):
    if port is not None:
        try:
            return DashboardServer((host, port), Handler)
        except OSError as e:
            if not platform_support.address_in_use(e):
                raise
            return DashboardServer((host, 0), Handler)
    # Default port: prefer the last-used port (keeps an installed Sidee
    # TV tile's address stable), then the fixed default, then any free
    # port. A busy candidate falls through to the next one.
    candidates = []
    if isinstance(saved_port, int) and 0 < saved_port < 65536:
        candidates.append(saved_port)
    if _PORT not in candidates:
        candidates.append(_PORT)
    for candidate in candidates:
        try:
            return DashboardServer((host, candidate), Handler)
        except OSError as e:
            if not platform_support.address_in_use(e):
                raise
    return DashboardServer((host, 0), Handler)


class Dashboard:
    """Own the dashboard socket and lifecycle, shared by both launchers."""

    def __init__(
        self,
        port: int | None = None,
        headless: bool = False,
        host: str = "0.0.0.0",
    ):
        # Reuse the saved identity so an installed Sidee TV tile keeps
        # working across restarts. The import-time ACCESS_KEY stays as
        # the fallback for the very first run.
        global ACCESS_KEY
        saved = _load_identity()
        if saved:
            ACCESS_KEY = saved["key"]
        self.server = _bind_dashboard_server(port, host, saved.get("port"))
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/?key={ACCESS_KEY}"
        self.stop_event = threading.Event()
        self.server.stop_event = self.stop_event
        self.server.headless = headless
        self.server.timeout = 0.2
        self.thread = None
        self.tile_thread = None
        self.error = None

    def start(self) -> None:
        try:
            _remember_dashboard(self.port)
            self.thread = threading.Thread(target=self._run, daemon=True,
                                           name="sidee-dashboard")
            self.thread.start()
        except BaseException:
            self.server.server_close()
            _forget_dashboard()
            raise
        # Identity saving is best-effort: a read-only profile dir must
        # never take down a dashboard that is already serving.
        try:
            _save_identity(ACCESS_KEY, self.port)
        except OSError:
            pass
        try:
            self.tile_thread = threading.Thread(
                target=self._ensure_sidee_tv_tile, daemon=True,
                name="sidee-tv-tile")
            self.tile_thread.start()
        except RuntimeError:
            pass

    def _run(self) -> None:
        try:
            while not self.stop_event.is_set():
                self.server.handle_request()
        except Exception as error:
            self.error = error
        finally:
            self.stop_event.set()

    def open(self) -> bool:
        return webbrowser.open(self.url)

    def _ensure_sidee_tv_tile(self) -> None:
        """Keep a Sidee TV tile on the paired TV, with zero user steps.

        Runs in the background for the dashboard's lifetime: every two
        minutes (first check after 30 seconds, so startup stays fast) it
        looks at the paired TV's tile list and installs the Sidee TV tile
        when it is missing or points at an old address. Reinstalling under
        the same tile id replaces the old tile instead of duplicating it.
        No pairing yet, TV unreachable, or any MQTT error: skip quietly
        and retry on the next cycle.
        """
        if self.stop_event.wait(30):
            return
        while not self.stop_event.is_set():
            try:
                self._ensure_sidee_tv_tile_once()
            except Exception:
                pass
            if self.stop_event.wait(120):
                return

    def _ensure_sidee_tv_tile_once(self) -> None:
        try:
            session = client.Session.load()
        except (client.AuthError, OSError):
            return  # no pairing yet (or a corrupt one): nothing to do
        try:
            tiles = client.list_tiles(session)
        except Exception:
            return  # TV unreachable: retry on the next cycle
        host_ip = _local_ip(session.host)
        try:
            address = ipaddress.ip_address(host_ip)
        except ValueError:
            return
        if address.is_loopback or address.is_unspecified:
            return  # no LAN route to the TV: a loopback tile is useless
        url = tv_frontend.absolute_tv_url(host_ip, self.port, ACCESS_KEY)
        if any(isinstance(t, dict) and
               client.tile_matches_request(t, "sidee_tv", url)
               for t in tiles):
            return
        try:
            client.add_tile(session, "sidee_tv", "Sidee TV", url, "")
        except Exception:
            return
        print("Sidee TV tile installed on your TV -- open it to browse "
              "and play with the remote.", flush=True)

    def close(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
        self.server.server_close()
        PAIRING.close()
        _forget_dashboard()


def serve(open_browser: bool = True, port: int | None = None,
          headless: bool = False) -> None:
    if _reopen_dashboard(open_browser):
        return
    dashboard = Dashboard(port, headless)
    previous_signals = {}
    try:
        dashboard.start()
        # Signal handlers set an event; cleanup runs outside the handler.
        if threading.current_thread() is threading.main_thread():
            for number in (signal.SIGINT, signal.SIGTERM):
                previous_signals[number] = signal.signal(
                    number, lambda *_: dashboard.stop_event.set())
        print(f"Sidee (this computer): {dashboard.url}", flush=True)
        print(f"Sidee (from your phone, same network): "
              f"http://{_local_ip()}:{dashboard.port}/?key={ACCESS_KEY}", flush=True)
        print("Use your phone: scan the QR code shown in the dashboard.")
        print("Keep the URL key private. Ctrl+C to quit.")
        if open_browser:
            dashboard.open()
        dashboard.stop_event.wait()
        if dashboard.error:
            raise dashboard.error
    except KeyboardInterrupt:
        pass
    finally:
        for number, handler in previous_signals.items():
            signal.signal(number, handler)
        dashboard.close()


def _local_ip(tv_host: str | None = None) -> str:
    """Choose a local interface without sending traffic or needing Internet.

    The TV route takes precedence over a VPN's default route. Before a TV
    has been selected, the local broadcast route selects a LAN interface.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if tv_host:
            s.connect((tv_host, client.MQTT_PORT))
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.connect((client.SSDP_BROADCAST, client.SSDP_PORT))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
