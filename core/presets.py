"""Preset catalog: apps ready to install with one click."""
from __future__ import annotations

import re
import ipaddress
from urllib.parse import quote, urlsplit, urlunsplit

PRESETS: dict[str, dict] = {
    "nuvio": {
        "name": "Nuvio",
        "app_id": "nuviodebug",
        "url": "https://nuviotvsmart.vercel.app/vidaa.html",
        # VIDAA launcher icons are square; the horizontal wordmark is stretched.
        "image": "https://nuviotvsmart.vercel.app/assets/images/tizenIcon.png",
        "icon": "assets/nuvio-wordmark.png",
        "description": "Browse and stream your library",
        "category": "Media",
    },
    "stremio": {
        "name": "Stremio",
        # Keep the existing Sidee app id so reinstalling replaces the old
        # web.stremio.com tile instead of leaving a duplicate behind.
        "app_id": "stremiodebug",
        "url": "https://noobygains.github.io/stremio-vidaa-tv/?install_source=sidee",
        "server_builder": "stremio",
        "server_optional": True,
        "server_placeholder": "Streaming server URL (optional)",
        # TV tile icon stays the community build's own URL (the TV fetches
        # it); the dashboard card uses the bundled copy below.
        "image": "https://noobygains.github.io/stremio-vidaa-tv/icon.png",
        "icon": "assets/stremio.png",
        "description": "Full Stremio TV for VIDAA with D-pad navigation",
        "category": "Media",
    },
    "jellyfin": {
        "name": "Jellyfin",
        "app_id": "jellyfin",
        "url": "",  # built from the user's server address
        "needs_server": True,
        "server_placeholder": "Your server's IP or URL",
        "image": "https://raw.githubusercontent.com/JohnCarter2021/Sidee/main/assets/jellyfin-tile-bold.png",
        "icon": "assets/jellyfin.png",
        "description": "Your media from your Jellyfin server",
        "category": "Media",
    },
    # --- Anime site indexes ---
    "everythingmoe": {
        "name": "EverythingMoe",
        "app_id": "everythingmoe",
        "url": "https://everythingmoe.com",
        "image": "https://everythingmoe.com/static/android-icon-48x48.png",
        "icon": "assets/logos/everythingmoe.png",
        "description": "Anime site index",
        "category": "Media",
    },
    "wotaku": {
        "name": "Wotaku",
        "app_id": "wotaku",
        "url": "https://wotaku.wiki",
        "image": "https://wotaku.wiki/asset/fav.svg",
        "icon": "assets/logos/wotaku.svg",
        "description": "Anime site index",
        "category": "Media",
    },
    "theindex": {
        "name": "The Index",
        "app_id": "theindex",
        "url": "https://theindex.moe",
        "image": "https://theindex.moe/_next/image?url=%2Ficons%2Flogo.png&w=64&q=75",
        "icon": "assets/logos/theindex.png",
        "description": "Anime site index",
        "category": "Media",
    },
    "justindex": {
        "name": "JustIndex",
        "app_id": "justindex",
        "url": "https://justindex.cc",
        "image": "https://justindex.cc/_next/image?url=%2F_next%2Fstatic%2Fmedia%2Flogo.bf43d9d4.png&w=128&q=75",
        "icon": "assets/logos/justindex.png",
        "description": "Anime site index",
        "category": "Media",
    },
    # --- Anime streaming sites ---
    "miruro": {
        "name": "Miruro",
        "app_id": "miruro",
        "url": "https://miruro.cx",
        "image": "https://miruro.cx/miruro-cat-halloween-v2.png",
        "icon": "assets/logos/miruro.png",
        "description": "High-speed soft/hard subbed anime with modern player controls",
        "category": "Anime",
    },
    "animepahe": {
        "name": "AnimePahe",
        "app_id": "animepahe",
        "url": "https://animepahe.pw/",
        "image": "https://raw.githubusercontent.com/JohnCarter2021/Sidee/main/assets/logos/animepahe.png",
        "icon": "assets/logos/animepahe.png",
        "description": "Ultra-lightweight anime streaming portal with clean video playback",
        "category": "Anime",
    },
    "mkissa": {
        "name": "MKissa",
        "app_id": "mkissa",
        "url": "https://mkissa.to",
        "image": "https://raw.githubusercontent.com/JohnCarter2021/Sidee/main/assets/logos/mkissa.png",
        "icon": "assets/logos/mkissa.png",
        "description": "Anime streaming - sub / dub",
        "category": "Media",
    },
    "anikototv": {
        "name": "AniKoto TV",
        "app_id": "anikototv",
        "url": "https://anikototv.to/home",
        "image": "https://anikototv.to/AnikotoTheme/assets/images/logo.png",
        "icon": "assets/logos/anikoto.png",
        "description": "TV-optimized anime experience with soft/hard subs, dubs and auto-play",
        "category": "Anime",
    },
    "reanime": {
        "name": "Re:ANIME",
        "app_id": "reanime",
        "url": "https://reanime.to/home",
        "image": "https://reanime.to/logo-halloween.png",
        "icon": "assets/logos/reanime.png",
        "description": "Subbed, dubbed and auto-next anime streaming hub with auto-skip",
        "category": "Anime",
    },
    "animex": {
        "name": "AnimeX",
        "app_id": "animex",
        "url": "https://animex.one",
        "image": "https://animex.one/misc/full-logo.png",
        "icon": "assets/logos/animex.png",
        "description": "Anime streaming - sub / dub / auto-next",
        "category": "Media",
    },
    "anipm": {
        "name": "AniPM",
        "app_id": "anipm",
        "url": "https://ani.pm",
        "image": "https://ani.pm/assets/ani-mark-Do_yx2BV.png",
        "icon": "assets/logos/anipm.png",
        "description": "Anime streaming - sub / dub",
        "category": "Media",
    },
    "nekowatch": {
        "name": "NekoWatch",
        "app_id": "nekowatch",
        "url": "https://nekowatch.xyz",
        "image": "https://raw.githubusercontent.com/JohnCarter2021/Sidee/main/assets/logos/nekowatch.png",
        "icon": "assets/logos/nekowatch.png",
        "description": "Anime streaming - sub / dub / auto-next",
        "category": "Media",
    },
    "anidap": {
        "name": "Anidap",
        "app_id": "anidap",
        "url": "https://anidap.lol",
        "image": "https://anidap.lol/assets/images/optimized/logo-160x160.webp",
        "icon": "assets/logos/anidap.png",
        "description": "Anime streaming - sub / dub / auto-next",
        "category": "Media",
    },
    "anistream": {
        "name": "Anistream",
        "app_id": "anistream",
        "url": "https://anistream.one",
        "image": "https://raw.githubusercontent.com/JohnCarter2021/Sidee/main/assets/logos/anistream.png",
        "icon": "assets/logos/anistream.png",
        "description": "Anime streaming - sub / dub / auto-next",
        "category": "Media",
    },
    # --- Movie / TV streaming aggregators ---
    "movy": {
        "name": "Movy",
        "app_id": "movy",
        "url": "https://www.movy.sx/",
        "image": "https://raw.githubusercontent.com/JohnCarter2021/Sidee/main/assets/logos/movy.png",
        "icon": "assets/logos/movy.png",
        "description": "Movies, TV shows and anime aggregator with 4K auto-next streams",
        "category": "Media",
    },
    "cinejoy": {
        "name": "Cinejoy",
        "app_id": "cinejoy",
        "url": "https://cinejoy.pk/",
        "image": "https://cinejoy.pk/brand/logomark-white.svg",
        "icon": "assets/logos/cinejoy.svg",
        "description": "Clean on-demand movie and TV series streaming with auto-next",
        "category": "Media",
    },
    "popcornmovies": {
        "name": "PopcornMovies",
        "app_id": "popcornmovies",
        "url": "https://popcornmovies.ac/",
        "image": "https://raw.githubusercontent.com/JohnCarter2021/Sidee/main/assets/logos/popcornmovies.png",
        "icon": "assets/logos/popcornmovies.png",
        "description": "Browse and stream trending blockbusters and TV shows with multi-servers",
        "category": "Media",
    },
    "flystream": {
        "name": "FlyStream",
        "app_id": "flystream",
        "url": "https://flystream.net/",
        "image": "https://raw.githubusercontent.com/JohnCarter2021/Sidee/main/assets/logos/flystream.png",
        "icon": "assets/logos/flystream.png",
        "description": "Multi-server movies and series streaming aggregator with 4K sources",
        "category": "Media",
    },
    "rivestream": {
        "name": "Rive",
        "app_id": "rivestream",
        "url": "https://www.rivestream.app/",
        "image": "https://raw.githubusercontent.com/JohnCarter2021/Sidee/main/assets/logos/rivestream.png",
        "icon": "assets/logos/rivestream.png",
        "description": "Fast streaming web app with high-resolution sources and clean layout",
        "category": "Media",
    },
    "sevenmovies": {
        "name": "7Movies",
        "app_id": "sevenmovies",
        "url": "https://7movies.ac/",
        "image": "https://raw.githubusercontent.com/JohnCarter2021/Sidee/main/assets/logos/sevenmovies.png",
        "icon": "assets/logos/sevenmovies.png",
        "description": "Full catalog of movies, series and anime with auto-next streaming",
        "category": "Media",
    },
}


def get(key: str) -> dict | None:
    return PRESETS.get(key.lower())


def is_private_host(server: str) -> bool:
    """True for local/private network (LAN) hosts: HTTP is allowed only there."""
    host = (urlsplit(server if "://" in server else "//" + server).hostname or "").rstrip(".")
    if host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in ipaddress.ip_network(network) for network in
               ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))


def build_server_url(server: str) -> str:
    """Server address -> web client URL, including scheme and path."""
    server = server.strip().rstrip("/")
    has_scheme = "://" in server
    parsed = urlsplit(server if has_scheme else "//" + server)
    host = (parsed.hostname or "").rstrip(".")
    if not host:
        raise ValueError("Enter your Jellyfin server's LAN IP or full URL.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if (host == "localhost" or host.endswith(".localhost") or
            (address and (address.is_loopback or address.is_unspecified))):
        raise ValueError("Use your Jellyfin server's LAN IP or URL; localhost "
                         "and loopback addresses refer to the TV itself.")
    port = parsed.port  # also rejects malformed or out-of-range ports
    scheme = parsed.scheme if has_scheme else ("http" if is_private_host(server) else "https")
    authority = parsed.netloc
    if not has_scheme and port is None:
        authority += ":8096"  # default Jellyfin port
    path = parsed.path.rstrip("/")
    if not re.search(r"/web(/index\.html)?$", path):
        path += "/web/index.html"
    return urlunsplit((scheme, authority, path, parsed.query, parsed.fragment))


def build_stremio_url(server: str = "") -> str:
    """Build the VIDAA-optimised full Stremio TV URL.

    This community TV build uses the Stremio Theater interface with a modern
    stremio-core-web engine and VIDAA-specific focus, keyboard and viewport
    fixes. Its server query parameter can point to a LAN Stremio server or
    to the Remote HTTPS URL exposed by Stremio Service/Desktop. Loopback
    addresses would point back to the TV.
    """
    base = "https://noobygains.github.io/stremio-vidaa-tv/?install_source=sidee"
    server = server.strip().rstrip("/")
    if not server:
        return base
    parsed = urlsplit(server)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(
            "Paste the full Stremio streaming server URL, including http:// or https://.")
    host = parsed.hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if (host == "localhost" or host.endswith(".localhost") or
            (address and (address.is_loopback or address.is_unspecified))):
        raise ValueError(
            "Use the Stremio server address reachable by your TV; localhost points to the TV itself.")
    normalized = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path or "", parsed.query, parsed.fragment))
    return base + "&server=" + quote(normalized, safe="")
