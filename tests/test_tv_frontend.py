"""TV front-end prototype: page rewrite, playlist rewrite, stream guard,
slug/episode parsing, and the sources-API resolution path. All offline:
network is mocked, the SSRF guard is tested with literal IPs only."""
import json
import os
import unittest
from unittest.mock import patch

from core import tv_frontend


class TestParsing(unittest.TestCase):
    def test_extract_slug_prefers_slug(self):
        html = 'x slug:"the-summer-hikaru-died-erx4l" animeId:"other"'
        self.assertEqual(tv_frontend.extract_slug(html),
                         "the-summer-hikaru-died-erx4l")

    def test_extract_slug_falls_back_to_anime_id(self):
        self.assertEqual(tv_frontend.extract_slug('animeId:"abc-123"'),
                         "abc-123")

    def test_extract_slug_none(self):
        self.assertIsNone(tv_frontend.extract_slug("<html></html>"))

    def test_episode_number(self):
        self.assertEqual(tv_frontend.episode_number(
            "https://animex.one/watch/the-summer-hikaru-died-177689-episode-12"), 12)
        self.assertIsNone(tv_frontend.episode_number(
            "https://animex.one/anime/the-summer-hikaru-died-177689"))

    def test_pretty_title(self):
        self.assertEqual(tv_frontend.pretty_title(
            "https://animex.one/watch/the-summer-hikaru-died-177689-episode-1"),
            "The Summer Hikaru Died")


class TestRewritePage(unittest.TestCase):
    SAMPLE = ('<html><head><title>T</title></head><body>'
              '<a href="/catalog">Cat</a>'
              '<a href="/watch/show-1-episode-2" target="_blank">Ep2</a>'
              '<a href="https://discord.gg/x">Chat</a>'
              '<img src="/img/logo.png">'
              '<a href="#top">Top</a>'
              '</body></html>')

    def test_links_rewritten_and_nav_injected(self):
        out = tv_frontend.rewrite_page(self.SAMPLE, "https://animex.one/",
                                       "KEY1")
        self.assertIn("/tv/page?u=https%3A%2F%2Fanimex.one%2Fcatalog", out)
        self.assertIn("/tv/play?watch=https%3A%2F%2Fanimex.one%2Fwatch%2Fshow-1-episode-2", out)
        self.assertIn("https://discord.gg/x", out)
        self.assertNotIn("target=", out)
        self.assertIn("https://animex.one/img/logo.png", out)
        self.assertIn("tv-focus", out)
        self.assertIn("ArrowLeft", out)

    def test_relative_links_resolve_against_page_url(self):
        out = tv_frontend.rewrite_page(
            '<a href="catalog">C</a>', "https://animex.one/home", "K")
        self.assertIn("/tv/page?u=https%3A%2F%2Fanimex.one%2Fcatalog", out)


class TestRewritePlaylist(unittest.TestCase):
    def test_segments_keys_and_comments(self):
        pl = ("#EXTM3U\n#EXT-X-VERSION:3\n"
              '#EXT-X-KEY:METHOD=AES-128,URI="keys/k1.key"\n'
              "seg1.ts\nhttps://cdn.example.com/v/seg2.ts\n"
              "#EXT-X-ENDLIST\n")
        out = tv_frontend.rewrite_playlist(
            pl, "https://cdn.example.com/v/master.m3u8", "K")
        self.assertIn("/tv/stream?u=https%3A%2F%2Fcdn.example.com%2Fv%2Fseg1.ts", out)
        self.assertIn("/tv/stream?u=https%3A%2F%2Fcdn.example.com%2Fv%2Fseg2.ts", out)
        self.assertIn('URI="/tv/stream?u=https%3A%2F%2Fcdn.example.com%2Fv%2Fkeys%2Fk1.key', out)
        self.assertIn("#EXT-X-ENDLIST", out)
        self.assertNotIn("\nseg1.ts\n", out)


class TestStreamGuard(unittest.TestCase):
    def setUp(self):
        # Guard tests must not depend on the machine's proxy env.
        self._env_patch = patch.dict(
            "os.environ",
            {k: v for k, v in os.environ.items()
             if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")},
            clear=True)
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()

    def test_private_and_loopback_rejected(self):
        for url in ("http://127.0.0.1/x.m3u8", "http://192.168.1.5/x",
                    "http://10.0.0.9/x", "http://169.254.1.2/x",
                    "ftp://example.com/x", "https:///x"):
            self.assertFalse(tv_frontend.stream_allowed(url), url)

    def test_public_literal_ip_allowed(self):
        self.assertTrue(tv_frontend.stream_allowed("http://93.184.216.34/x"))

    def test_unresolvable_rejected(self):
        self.assertFalse(tv_frontend.stream_allowed("https://invalid.invalid/x"))

    def test_dns_name_allowed_when_proxy_configured(self):
        with patch.dict("os.environ",
                        {"https_proxy": "http://proxy.example:3128"}):
            self.assertTrue(tv_frontend.stream_allowed(
                "https://cdn.example.com/v/seg1.ts"))


class TestResolveStream(unittest.TestCase):
    def test_returns_mpegurl_source(self):
        body = json.dumps({"sources": [
            {"url": "https://cdn.example.com/a.m3u8",
             "type": "application/vnd.apple.mpegurl"},
            {"url": "https://cdn.example.com/b.mp4", "type": "video/mp4"},
        ]}).encode()
        with patch.object(tv_frontend, "_http_get",
                          return_value=(200, {}, body)):
            self.assertEqual(tv_frontend.resolve_stream("slug-x", 1),
                             "https://cdn.example.com/a.m3u8")

    def test_empty_sources_raises(self):
        body = json.dumps({"sources": []}).encode()
        with patch.object(tv_frontend, "_http_get",
                          return_value=(200, {}, body)):
            with self.assertRaises(tv_frontend.TvError):
                tv_frontend.resolve_stream("slug-x", 1)

    def test_non_200_raises(self):
        with patch.object(tv_frontend, "_http_get",
                          return_value=(404, {}, b"")):
            with self.assertRaises(tv_frontend.TvError):
                tv_frontend.resolve_stream("slug-x", 1)


class TestPageAndPlay(unittest.TestCase):
    def test_fetch_page_rejects_other_hosts(self):
        with self.assertRaises(tv_frontend.TvError):
            tv_frontend.fetch_page("https://evil.example.com/")

    def test_fetch_page_rejects_empty_body(self):
        with patch.object(tv_frontend, "_http_get",
                          return_value=(200, {}, b"")):
            with self.assertRaises(tv_frontend.TvError):
                tv_frontend.fetch_page("https://animex.one/")

    def test_http_get_retries_empty_read(self):
        returns = [(200, {}, b""), (200, {}, b""),
                   (200, {}, b"<html>ok</html>")]
        with patch.object(tv_frontend, "_request",
                          side_effect=returns) as mock:
            status, _h, body = tv_frontend._http_get("https://animex.one/", {})
        self.assertEqual((status, body), (200, b"<html>ok</html>"))
        self.assertEqual(mock.call_count, 3)

    def test_http_get_retries_truncated_body(self):
        returns = [(200, {"Content-Length": "100"}, b"<html>cut"),
                   (200, {"Content-Length": "17"}, b"<html>full</html>")]
        with patch.object(tv_frontend, "_request",
                          side_effect=returns) as mock:
            status, _h, body = tv_frontend._http_get("https://animex.one/", {})
        self.assertEqual((status, body), (200, b"<html>full</html>"))
        self.assertEqual(mock.call_count, 2)

    def test_request_sends_no_urllib_defaults(self):
        import os
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                seen.update(self.headers)
                body = b"hello"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {k: v for k, v in os.environ.items()
                   if k.lower() not in ("http_proxy", "https_proxy",
                                        "all_proxy")}
            with patch.dict(os.environ, env, clear=True):
                status, _h, body = tv_frontend._request(
                    f"http://127.0.0.1:{server.server_address[1]}/x", {})
        finally:
            server.shutdown()
        self.assertEqual((status, body), (200, b"hello"))
        self.assertIsNone(seen.get("Accept-Encoding"))
        self.assertNotEqual(seen.get("Connection"), "close")
        self.assertEqual(seen.get("User-Agent"),
                         tv_frontend.UA["User-Agent"])

    def test_play_response_renders_player(self):
        watch = "https://animex.one/watch/the-summer-hikaru-died-177689-episode-1"
        with patch.object(tv_frontend, "fetch_page",
                          return_value='slug:"the-summer-hikaru-died-erx4l"'), \
             patch.object(tv_frontend, "resolve_stream",
                          return_value="https://cdn.example.com/a.m3u8"):
            code, ctype, body = tv_frontend.play_response(watch, "K")
        self.assertEqual(code, 200)
        text = body.decode()
        self.assertIn("<video", text)
        self.assertIn("/tv/stream?u=https%3A%2F%2Fcdn.example.com%2Fa.m3u8", text)
        self.assertIn("The Summer Hikaru Died", text)
        self.assertIn("/tv/page?u=https%3A%2F%2Fanimex.one%2Fanime%2Fthe-summer-hikaru-died-177689", text)
        self.assertIn("hls.js", text)

    def test_page_response_delegates_watch_urls(self):
        with patch.object(tv_frontend, "play_response",
                          return_value=(200, "text/html", b"PLAYER")) as mock:
            code, _ctype, body = tv_frontend.page_response(
                "https://animex.one/watch/x-1-episode-1", "K")
        self.assertEqual((code, body), (200, b"PLAYER"))
        mock.assert_called_once()


class TestStreamResponse(unittest.TestCase):
    def test_playlist_is_rewritten(self):
        pl = b"#EXTM3U\nseg1.ts\n"
        with patch.object(tv_frontend, "fetch_stream",
                          return_value=(200, "application/vnd.apple.mpegurl", None, pl)):
            code, ctype, _cr, body = tv_frontend.stream_response(
                "https://cdn.example.com/v/m.m3u8", None, "K")
        self.assertEqual(code, 200)
        self.assertIn(b"/tv/stream?u=https%3A%2F%2Fcdn.example.com%2Fv%2Fseg1.ts",
                      body)

    def test_segment_passes_through(self):
        with patch.object(tv_frontend, "fetch_stream",
                          return_value=(200, "video/MP2T", None, b"\x00\x01")):
            code, _ctype, _cr, body = tv_frontend.stream_response(
                "https://cdn.example.com/v/seg1.ts", None, "K")
        self.assertEqual((code, body), (200, b"\x00\x01"))

    def test_disallowed_stream_is_502(self):
        code, _ctype, _cr, _body = tv_frontend.stream_response(
            "http://127.0.0.1/x.m3u8", None, "K")
        self.assertEqual(code, 502)


class TestPlayerPage(unittest.TestCase):
    def test_hint_survives_manifest_and_fatal_errors_retry(self):
        html = tv_frontend.player_page(
            "Show", 3, "/tv/stream?u=x&key=k", "/tv/page?u=y&key=k", "k")
        # The hint must NOT hide on manifest parse: autoplay blocks and
        # manifest failures otherwise leave a black screen with no hint.
        self.assertIn(
            "MANIFEST_PARSED,function(){v.play().catch(function(){});}",
            html)
        self.assertNotIn(
            "MANIFEST_PARSED,function(){v.play().catch(function(){});"
            "hideMsg();}", html)
        # A fatal stream error shows a readable message and OK reloads
        # for a fresh resolve instead of sitting on black.
        self.assertIn("Hls.Events.ERROR", html)
        self.assertIn("Stream failed to load. Press OK to try again.", html)
        self.assertIn("window.location.reload()", html)
        # Library from the phone first, CDN only as a fallback.
        self.assertIn("/tv/hls.js?key=k", html)
        self.assertIn("cdn.jsdelivr.net/npm/hls.js@1", html)


class TestDiagAndHls(unittest.TestCase):
    def test_diag_page_rows_and_es5_script(self):
        html = tv_frontend.diag_page("k")
        for row in ("row-js", "row-ua", "row-hls", "row-mse", "row-native",
                    "row-mp4", "row-menu", "row-hlsphone", "row-cdn",
                    "row-key"):
            self.assertIn(row, html)
        self.assertIn("/tv/diag", tv_frontend.menu_page("k"))
        self.assertIn("Check this TV", tv_frontend.menu_page("k"))
        # Old TV browsers: no arrow functions, no fetch API.
        self.assertNotIn("=>", html)
        self.assertNotIn("fetch(", html)
        self.assertIn("XMLHttpRequest", html)

    def test_hls_response_caches_and_fails_cleanly(self):
        tv_frontend._hls_cache = None
        with patch.object(tv_frontend, "_request",
                          return_value=(200, {}, b"var Hls={};")) as get:
            code, ctype, body = tv_frontend.hls_response()
            self.assertEqual((code, ctype, body),
                             (200, "application/javascript", b"var Hls={};"))
            tv_frontend.hls_response()
            get.assert_called_once()
        tv_frontend._hls_cache = None
        with patch.object(tv_frontend, "_request",
                          side_effect=OSError("down")):
            with self.assertRaises(tv_frontend.TvError):
                tv_frontend.hls_response()


if __name__ == "__main__":
    unittest.main()
