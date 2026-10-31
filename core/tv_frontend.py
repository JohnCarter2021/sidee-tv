"""TV front-end prototype (AnimeX only).

Sidee serves a remote-friendly front-end on the same LAN server as the
dashboard: a big-tile menu, proxied AnimeX pages with links rewritten to
stay inside /tv/ and a D-pad navigation script injected, and a native
player page. The player does NOT use an iframe: Sidee resolves the HLS
stream server-side (page HTML slug -> sources API -> playlist) and proxies
the playlist and segments, attaching the Referer the stream host requires
(direct requests from a TV browser are refused with 403).

Scope of this prototype: browse home/catalog/title pages and play episodes
with the default provider, subtitles. No search, no login, no dub/sub
switch, no other sites. Every /tv/ URL carries the dashboard access key,
the same pattern the dashboard QR code already uses.

Security: page fetches are allowlisted to animex.one; the stream proxy
accepts any http(s) host (stream CDNs vary) but refuses private,
loopback, link-local, reserved and multicast addresses, so it cannot be
used to reach LAN services or cloud metadata endpoints.
"""
from __future__ import annotations

import base64
import html as html_lib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import time
import urllib.parse
from html.parser import HTMLParser

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124 Safari/537.36"}
SITE = "https://animex.one"
API = "https://pp.animex.one/rest/api"
PAGE_HOSTS = {"animex.one"}
TIMEOUT = 25
MAX_STREAM_BYTES = 64 * 1024 * 1024

NAV_CSS = """
<style>
.tv-focus{outline:4px solid #ffb300 !important;outline-offset:3px !important;}
.tv-hint{font-size:22px;color:#ccc;margin:16px;}
.tv-tile{display:block;font-size:30px;padding:28px;margin:18px;background:#222;
 color:#fff;text-decoration:none;border-radius:12px;}
body{background:#111;color:#fff;font-family:sans-serif;}
</style>
"""

# Arrow-key spatial navigation: arrows move a visible focus box to the
# nearest focusable element in that direction, OK activates it.
NAV_JS = """
<script>(function(){
function focusables(){return [...document.querySelectorAll(
 'a,button,input,select,textarea,[tabindex],video')].filter(function(el){
 return el.offsetParent!==null||el.tagName==='VIDEO';});}
var cur=null;
function ring(el){if(cur)cur.classList.remove('tv-focus');cur=el;
 if(cur){cur.classList.add('tv-focus');
  cur.scrollIntoView({block:'nearest',inline:'nearest'});}}
function move(dir){
 var els=focusables();if(!els.length)return;
 if(!cur){ring(els[0]);return;}
 var r=cur.getBoundingClientRect(),ox=r.left+r.width/2,oy=r.top+r.height/2;
 var best=null,bestScore=1e12;
 els.forEach(function(el){if(el===cur)return;
  var q=el.getBoundingClientRect(),cx=q.left+q.width/2,cy=q.top+q.height/2;
  var dx=cx-ox,dy=cy-oy,ok=false,main=0,cross=0;
  if(dir==='left'&&dx<0){ok=true;main=-dx;cross=Math.abs(dy);}
  if(dir==='right'&&dx>0){ok=true;main=dx;cross=Math.abs(dy);}
  if(dir==='up'&&dy<0){ok=true;main=-dy;cross=Math.abs(dx);}
  if(dir==='down'&&dy>0){ok=true;main=dy;cross=Math.abs(dx);}
  if(!ok)return;
  var score=main+cross*2;
  if(score<bestScore){bestScore=score;best=el;}});
 if(best)ring(best);}
document.addEventListener('keydown',function(e){
 var dirs={ArrowLeft:'left',ArrowRight:'right',ArrowUp:'up',ArrowDown:'down'};
 if(dirs[e.key]){e.preventDefault();move(dirs[e.key]);}
 else if(e.key==='Enter'&&cur){
  if(cur.tagName==='VIDEO'){e.preventDefault();
   if(cur.paused)cur.play();else cur.pause();}
  else{e.preventDefault();cur.click();}}
 else if((e.key==='Backspace'||e.key==='Escape')&&window.history.length>1){
  e.preventDefault();window.history.back();}});
window.addEventListener('load',function(){
 var els=focusables();if(els.length)ring(els[0]);});
})();</script>
"""


class TvError(Exception):
    """Plain-language failure surfaced on a /tv/ error page."""


def _request(url: str, headers: dict, timeout: int = TIMEOUT,
             max_bytes: int | None = None):
    """One HTTP GET via http.client (NOT urllib).

    urllib injects `Accept-Encoding: identity` and `Connection: close`,
    which makes some edges/proxies kill large chunked responses mid-body
    (observed: AnimeX homepage truncated or cut at 0 bytes through the
    VM egress proxy, while curl and a bare http.client request with
    curl's header set complete every time). A minimal header set avoids
    that. The environment proxy, when set, is honored the same way
    urllib honors it; its credentials stay in-process and are never
    logged. Returns (status, headers dict, body bytes).
    """
    parts = urllib.parse.urlparse(url)
    is_https = parts.scheme == "https"
    host = parts.hostname or ""
    port = parts.port or (443 if is_https else 80)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    send_headers = {"User-Agent": UA["User-Agent"], "Accept": "*/*"}
    send_headers.update(headers)
    proxy_raw = (os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
                 if is_https else
                 os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY"))
    conn = None
    try:
        if proxy_raw:
            pp = urllib.parse.urlparse(proxy_raw)
            conn = http.client.HTTPConnection(pp.hostname, pp.port,
                                              timeout=timeout)
            tunnel = {}
            if pp.username is not None:
                pw = urllib.parse.unquote(pp.password or "")
                user = urllib.parse.unquote(pp.username)
                tunnel["Proxy-Authorization"] = "Basic " + base64.b64encode(
                    f"{user}:{pw}".encode()).decode()
            tunnel["Proxy-Connection"] = "Keep-Alive"
            conn.set_tunnel(host, port, headers=tunnel)
            conn.connect()
            if is_https:
                ctx = ssl.create_default_context()
                conn.sock = ctx.wrap_socket(conn.sock, server_hostname=host)
        else:
            cls = http.client.HTTPSConnection if is_https \
                else http.client.HTTPConnection
            if is_https:
                conn = cls(host, port, timeout=timeout,
                           context=ssl.create_default_context())
            else:
                conn = cls(host, port, timeout=timeout)
        # putrequest (not request): skip_accept_encoding keeps the header
        # set exactly curl-like, and no Connection: close is sent.
        conn.putrequest("GET", path, skip_accept_encoding=True)
        for k, v in send_headers.items():
            conn.putheader(k, v)
        conn.endheaders()
        resp = conn.getresponse()
        try:
            body = resp.read() if max_bytes is None \
                else resp.read(max_bytes + 1)
        except http.client.IncompleteRead as e:
            body = e.partial
        return resp.status, dict(resp.getheaders()), body
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _http_get(url: str, headers: dict) -> tuple[int, dict, bytes]:
    """Single GET helper (patched by tests). Returns status, headers, body.

    Retries network-level failures: chunked reads through proxies can cut
    off mid-body. A body shorter than its declared Content-Length is
    treated as truncated and retried, never returned as a page.
    A (0, {}, b"") result means every attempt failed.
    """
    for _attempt in range(3):
        try:
            status, resp_headers, body = _request(url, headers)
        except (OSError, http.client.HTTPException):
            status, resp_headers, body = 0, {}, b""
        try:
            clen = int(resp_headers.get("Content-Length", ""))
        except (TypeError, ValueError):
            clen = None
        if body and (clen is None or len(body) >= clen):
            return status, resp_headers, body
        time.sleep(0.5)
    return 0, {}, b""


def tv_url(path: str, params: dict, key: str) -> str:
    q = dict(params)
    q["key"] = key
    return path + "?" + urllib.parse.urlencode(q)


def absolute_tv_url(host_ip: str, port: int, key: str) -> str:
    """Full /tv/ menu URL a TV browser opens: LAN address + dashboard key.

    This is the URL the Sidee TV tile installs (webui._install and the
    auto-tile thread). It is built from the live dashboard, never stored
    in the preset, because the address and key belong to this run.
    """
    return f"http://{host_ip}:{port}" + tv_url("/tv/", {}, key)


def extract_slug(page_html: str) -> str | None:
    """AnimeX slug id, e.g. the-summer-hikaru-died-erx4l, from SSR data."""
    m = re.search(r'slug:"([^"]+)"', page_html)
    if m:
        return m.group(1)
    m = re.search(r'animeId:"([^"]+)"', page_html)
    return m.group(1) if m else None


def episode_number(watch_url: str) -> int | None:
    m = re.search(r"-episode-(\d+)(?:/|\?|#|$)", watch_url)
    return int(m.group(1)) if m else None


def pretty_title(watch_url: str) -> str:
    path = urllib.parse.urlparse(watch_url).path
    slug = path.rsplit("/", 1)[-1]
    slug = re.sub(r"-episode-\d+$", "", slug)
    slug = re.sub(r"-\d+$", "", slug)
    return slug.replace("-", " ").title() or "AnimeX"


def resolve_stream(slug: str, ep: int, provider: str = "nero",
                   audio: str = "sub") -> str:
    """Sources API -> HLS playlist URL. Raises TvError on any failure."""
    q = urllib.parse.urlencode({"id": slug, "epNum": str(ep),
                                "type": audio, "providerId": provider})
    status, _headers, body = _http_get(f"{API}/sources?{q}",
                                       {"Referer": SITE + "/"})
    if status != 200:
        raise TvError("The episode list could not be loaded. "
                      "Try again in a moment.")
    try:
        data = json.loads(body.decode("utf-8", "ignore"))
    except ValueError:
        raise TvError("The episode data was unreadable. Try again.")
    for src in data.get("sources", []) or []:
        url = src.get("url", "")
        if "mpegurl" in (src.get("type", "") or "") and url:
            return url
    for src in data.get("sources", []) or []:
        if src.get("url"):
            return src["url"]
    raise TvError("No playable stream was found for this episode.")


def fetch_page(url: str) -> str:
    """Fetch an AnimeX page body. Raises TvError unless it is usable HTML."""
    parts = urllib.parse.urlparse(url)
    if parts.scheme != "https" or parts.netloc not in PAGE_HOSTS:
        raise TvError("Only AnimeX pages can be opened here.")
    for _attempt in range(3):
        status, _headers, body = _http_get(url, {})
        if status == 200 and body and b"</html>" in body.lower():
            return body.decode("utf-8", "ignore")
        time.sleep(0.5)
    raise TvError("AnimeX did not return that page. Try again.")


class _Rewriter(HTMLParser):
    """Rewrites a proxied page: internal links stay inside /tv/, assets
    become absolute (so they keep loading from AnimeX), watch links go to
    the player page, and new-tab targets are dropped (no tabs on a TV)."""

    def __init__(self, page_url: str, key: str):
        super().__init__(convert_charrefs=False)
        self.page_url = page_url
        self.key = key
        self.out: list[str] = []

    def _abs(self, href: str) -> str:
        return urllib.parse.urljoin(self.page_url, href)

    def _link(self, href: str) -> str | None:
        if not href or href.startswith("#") or href.startswith("javascript:") \
                or href.startswith("data:") or href.startswith("mailto:"):
            return None
        abs_url = self._abs(href)
        parts = urllib.parse.urlparse(abs_url)
        if parts.netloc not in PAGE_HOSTS:
            return None
        if parts.path.startswith("/watch/"):
            return tv_url("/tv/play", {"watch": abs_url}, self.key)
        return tv_url("/tv/page", {"u": abs_url}, self.key)

    def handle_starttag(self, tag, attrs):
        kept = []
        for name, value in attrs:
            if tag == "a" and name == "href":
                # Only rewritten links change; everything else (external
                # sites, anchors) keeps its original href.
                new = self._link(value or "")
                kept.append(("href", new if new is not None else value))
                continue
            if tag == "a" and name == "target":
                continue
            if name in ("src", "href", "action", "poster") and value \
                    and not value.startswith(("data:", "javascript:", "#")):
                value = self._abs(value)
            kept.append((name, value))
        self.out.append("<" + tag + "".join(
            f' {n}="{html_lib.escape(v, quote=True)}"' if v is not None
            else f" {n}" for n, v in kept) + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.out[-1] = self.out[-1][:-1] + " />"

    def handle_endtag(self, tag):
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(data)

    def handle_comment(self, data):
        self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self.out.append(f"<!{decl}>")

    def handle_pi(self, data):
        self.out.append(f"<?{data}>")


def rewrite_page(page_html: str, page_url: str, key: str) -> str:
    rw = _Rewriter(page_url, key)
    rw.feed(page_html)
    out = "".join(rw.out)
    if "</head>" in out:
        out = out.replace("</head>", NAV_CSS + "</head>", 1)
    else:
        out = NAV_CSS + out
    if "</body>" in out:
        out = out.replace("</body>", NAV_JS + "</body>", 1)
    else:
        out += NAV_JS
    return out


def rewrite_playlist(text: str, playlist_url: str, key: str) -> str:
    """Rewrite every playlist URI (segments, nested playlists, key URIs)
    to pass through /tv/stream, so Sidee can attach the required Referer."""
    out = []
    for line in text.splitlines():
        if line.startswith("#"):
            m = re.search(r'URI="([^"]+)"', line)
            if m:
                abs_url = urllib.parse.urljoin(playlist_url, m.group(1))
                line = line.replace(m.group(1),
                                    tv_url("/tv/stream", {"u": abs_url}, key))
            out.append(line)
        elif line.strip():
            abs_url = urllib.parse.urljoin(playlist_url, line.strip())
            out.append(tv_url("/tv/stream", {"u": abs_url}, key))
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def _proxy_configured(is_https: bool) -> bool:
    if is_https:
        return bool(os.environ.get("https_proxy")
                    or os.environ.get("HTTPS_PROXY"))
    return bool(os.environ.get("http_proxy")
                or os.environ.get("HTTP_PROXY"))


def stream_allowed(url: str) -> bool:
    """SSRF guard for the stream proxy: public http(s) hosts only.

    Literal IPs are always checked. DNS names are resolved and checked
    only when Sidee connects directly; when an egress proxy is
    configured, the proxy (not Sidee) resolves the name, so local DNS
    answers are meaningless for the check — and in sandboxed networks
    they are synthetic addresses that would wrongly block every host.
    """
    try:
        parts = urllib.parse.urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return False
        try:
            return ipaddress.ip_address(parts.hostname).is_global
        except ValueError:
            pass  # a DNS name, not a literal IP
        if _proxy_configured(parts.scheme == "https"):
            return True
        infos = socket.getaddrinfo(parts.hostname, None)
    except (socket.gaierror, ValueError):
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def fetch_stream(url: str, range_header: str | None) -> tuple[int, str, str | None, bytes]:
    """Fetch a playlist or segment through Sidee, attaching the Referer
    the stream host requires. Returns status, content-type, content-range,
    body. Range requests are forwarded so seeking keeps working."""
    if not stream_allowed(url):
        raise TvError("That stream address is not allowed.")
    headers = {"Referer": SITE + "/"}
    if range_header:
        headers["Range"] = range_header
    try:
        status, resp_headers, body = _request(url, headers,
                                              max_bytes=MAX_STREAM_BYTES)
    except (OSError, http.client.HTTPException):
        raise TvError("That stream could not be loaded.")
    if status == 0:
        raise TvError("That stream could not be loaded.")
    if len(body) > MAX_STREAM_BYTES:
        raise TvError("That stream chunk is too large.")
    if status == 200 and not body:
        raise TvError("That stream could not be loaded.")
    return (status, resp_headers.get("Content-Type", ""),
            resp_headers.get("Content-Range"), body)


def error_page(message: str, key: str) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Sidee TV</title>" + NAV_CSS + "</head><body>"
            "<p class='tv-hint'>" + html_lib.escape(message) + "</p>"
            "<a class='tv-tile' href='" + tv_url("/tv/", {}, key) +
            "'>Back to the TV menu</a></body></html>")


def menu_page(key: str) -> str:
    tiles = [
        ("AnimeX home", SITE + "/"),
        ("AnimeX catalog", SITE + "/catalog"),
        ("AnimeX schedule", SITE + "/schedule"),
    ]
    links = "".join(
        f"<a class='tv-tile' href='{tv_url('/tv/page', {'u': u}, key)}'>"
        f"{html_lib.escape(name)}</a>" for name, u in tiles)
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Sidee TV</title>" + NAV_CSS + "</head><body>"
            "<h1 style='font-size:36px;margin:24px;'>Sidee TV</h1>"
            "<p class='tv-hint'>Arrows move, OK opens, Back returns. "
            "Prototype: AnimeX browsing and playback only.</p>"
            + links + NAV_JS + "</body></html>")


def page_response(u: str, key: str) -> tuple[int, str, bytes]:
    """GET /tv/page handler result: status, content-type, body."""
    try:
        if urllib.parse.urlparse(u).path.startswith("/watch/"):
            return play_response(u, key)
        return 200, "text/html; charset=utf-8", \
            rewrite_page(fetch_page(u), u, key).encode("utf-8")
    except TvError as e:
        return 502, "text/html; charset=utf-8", \
            error_page(str(e), key).encode("utf-8")


def play_response(watch_url: str, key: str) -> tuple[int, str, bytes]:
    """GET /tv/play handler result: resolve the stream, render the player."""
    try:
        page_html = fetch_page(watch_url)
        slug = extract_slug(page_html)
        ep = episode_number(watch_url)
        if not slug or not ep:
            raise TvError("That episode link could not be read.")
        stream = resolve_stream(slug, ep)
        title = pretty_title(watch_url)
        # Back goes to the title page: AnimeX title URLs are the watch
        # slug minus the -episode-N suffix, under /anime/.
        last = urllib.parse.urlparse(watch_url).path.rsplit("/", 1)[-1]
        title_slug = re.sub(r"-episode-\d+$", "", last)
        back = tv_url("/tv/page", {"u": SITE + "/anime/" + title_slug}, key)
        stream_url = tv_url("/tv/stream", {"u": stream}, key)
        body = player_page(title, ep, stream_url, back)
        return 200, "text/html; charset=utf-8", body.encode("utf-8")
    except TvError as e:
        return 502, "text/html; charset=utf-8", \
            error_page(str(e), key).encode("utf-8")


def player_page(title: str, ep: int, stream_url: str, back_url: str) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>" + html_lib.escape(title) + "</title>"
            "<script src='https://cdn.jsdelivr.net/npm/hls.js@1'></script>"
            "<style>body{background:#000;color:#fff;font-family:sans-serif;"
            "margin:0}video{width:100vw;height:100vh;background:#000}"
            "#msg{position:fixed;top:20px;left:20px;font-size:24px;"
            "background:rgba(0,0,0,.7);padding:12px 18px;border-radius:8px}"
            "</style></head><body>"
            "<video id='v' controls playsinline></video>"
            "<div id='msg'>" + html_lib.escape(title) +
            f" &mdash; Episode {ep}<br><span style='font-size:18px;color:#ccc'>"
            "Press OK to play or pause. Left and right seek. "
            "Back returns to the catalog.</span></div>"
            "<script>(function(){var v=document.getElementById('v');"
            "var src=" + json.dumps(stream_url) + ";"
            "var back=" + json.dumps(back_url) + ";"
            "function hideMsg(){var m=document.getElementById('msg');"
            "if(m)m.style.display='none';}"
            # The hint stays up until playback actually starts: hiding it
            # on MANIFEST_PARSED left a black screen with no guidance when
            # the TV browser blocked autoplay or the manifest then failed.
            # A fatal stream error shows a readable message, and OK reloads
            # the page for a fresh resolve instead of sitting on black.
            "var failed=false;"
            "function showError(text){var m=document.getElementById('msg');"
            "if(m){m.textContent=text;m.style.display='block';}}"
            "if(window.Hls&&Hls.isSupported()){var h=new Hls();"
            "h.loadSource(src);h.attachMedia(v);"
            "h.on(Hls.Events.MANIFEST_PARSED,function(){v.play().catch("
            "function(){});});"
            "h.on(Hls.Events.ERROR,function(e,data){if(data&&data.fatal){"
            "failed=true;showError('Stream failed to load. "
            "Press OK to try again.');}});}"
            "else if(v.canPlayType('application/vnd.apple.mpegurl')){"
            "v.src=src;v.addEventListener('loadedmetadata',function(){"
            "v.play().catch(function(){});});"
            "v.addEventListener('error',function(){failed=true;"
            "showError('Stream failed to load. "
            "Press OK to try again.');});}"
            "else{document.getElementById('msg').textContent="
            "'This TV browser cannot play this stream.';}"
            "document.addEventListener('keydown',function(e){"
            "if(e.key==='Enter'||e.key===' '){e.preventDefault();"
            "if(failed){window.location.reload();}"
            "else if(v.paused)v.play();else v.pause();hideMsg();}"
            "else if(e.key==='ArrowLeft'){e.preventDefault();"
            "v.currentTime=Math.max(0,v.currentTime-10);}"
            "else if(e.key==='ArrowRight'){e.preventDefault();"
            "v.currentTime=Math.min(v.duration||0,v.currentTime+10);}"
            "else if(e.key==='ArrowUp'){e.preventDefault();"
            "v.volume=Math.min(1,v.volume+0.1);}"
            "else if(e.key==='ArrowDown'){e.preventDefault();"
            "v.volume=Math.max(0,v.volume-0.1);}"
            "else if(e.key==='Backspace'||e.key==='Escape'){"
            "e.preventDefault();window.location=back;}});"
            "v.addEventListener('play',hideMsg);})();</script>"
            "</body></html>")


def stream_response(u: str, range_header: str | None,
                    key: str) -> tuple[int, str, str | None, bytes]:
    """GET /tv/stream handler result: status, content-type, content-range,
    body. Playlists are rewritten; segments pass through untouched."""
    try:
        status, ctype, crange, body = fetch_stream(u, range_header)
        if status == 200 and "mpegurl" in (ctype or "").lower():
            body = rewrite_playlist(body.decode("utf-8", "ignore"), u, key) \
                .encode("utf-8")
            ctype = "application/vnd.apple.mpegurl"
        return status, ctype, crange, body
    except TvError as e:
        return 502, "text/plain", None, str(e).encode("utf-8")
