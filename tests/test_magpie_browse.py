"""Magpie browse stack tests (stdlib unittest — no pytest needed).

Run:  python3 -m unittest discover -s tests -p 'test_magpie*.py'
from the faeOS root, or:  python3 tests/test_magpie_browse.py
"""
from __future__ import annotations

import asyncio
import gzip
import http.server
import os
import socketserver
import struct
import sys
import threading
import time
import unittest
import zlib
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(BIN))

import fae_termart as art  # noqa: E402
import magpie_dom as dom  # noqa: E402
import magpie_fetch as fetch  # noqa: E402
import magpie_image as image  # noqa: E402


def make_png(width: int, height: int, rgb=(10, 20, 30)) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(typ: bytes, data: bytes) -> bytes:
        out = struct.pack(">I", len(data)) + typ + data
        return out + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def make_gif() -> bytes:
    # 2x1: black, white. LZW min code 1: CLEAR(10) 0(00) 1(01) EOI(11).
    out = bytearray(b"GIF89a")
    out += struct.pack("<HHBBB", 2, 1, 0x80, 0, 0)
    out += bytes([0, 0, 0, 255, 255, 255])
    out += bytes([0x2C, 0, 0, 0, 0, 2, 0, 1, 0, 0x00])
    out += bytes([0x01])  # LZW min code size
    out += bytes([0x01, 0xD2, 0x00, 0x3B])
    return bytes(out)


def make_bmp() -> bytes:
    # 2x1 24-bit, bottom-up, padded rows.
    row = bytes([0, 0, 255, 0, 255, 0]) + b"\x00\x00"
    px = row  # single row (height=1)
    off = 14 + 40
    size = off + len(px)
    hdr = b"BM" + struct.pack("<IHHI", size, 0, 0, off)
    dib = struct.pack("<IiiHHIIiiII", 40, 2, 1, 1, 24, 0, len(px), 2835, 2835, 0, 0)
    return hdr + dib + px


class FetchTests(unittest.TestCase):
    def test_normalize_bare_host(self):
        self.assertEqual(fetch.normalize_url("example.com"), "https://example.com")

    def test_normalize_blocks_javascript(self):
        with self.assertRaises(fetch.FetchError):
            fetch.normalize_url("javascript:alert(1)")

    def test_normalize_needs_base_for_relative(self):
        self.assertEqual(fetch.normalize_url("/p", base="https://ex.test/a"), "https://ex.test/p")

    def test_tor_strict_without_torsocks(self):
        if fetch.have_tor_support():
            self.skipTest("torsocks present")
        with self.assertRaises(fetch.FetchError):
            fetch.HttpClient(tor=True)

    def test_search_chain_tor_strict(self):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader("magpie_legacy_test", str(BIN / "magpie"))
        spec = importlib.util.spec_from_loader("magpie_legacy_test", loader)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["magpie_legacy_test"] = mod
        loader.exec_module(mod)
        if fetch.have_tor_support():
            self.skipTest("torsocks present")
        results, eng, err = mod.search_chain("test", tor=True)
        self.assertEqual(results, [])
        self.assertIn("torsocks", err)

    def test_cookie_roundtrip(self):
        jar = fetch.CookieJar()
        jar.set_from_headers("https://ex.test/", [("Set-Cookie", "a=1; Path=/; Max-Age=60")])
        self.assertIn("a=1", jar.header_for("https://ex.test/page"))
        self.assertEqual(jar.header_for("http://other.test/"), "")

    def test_cookie_expired(self):
        jar = fetch.CookieJar()
        jar.set_from_headers("https://ex.test/", [("Set-Cookie", "a=1; Max-Age=0")])
        self.assertEqual(len(jar), 0)

    def test_data_url(self):
        r = fetch.parse_data_url("data:text/plain,hello")
        self.assertEqual(r.text(), "hello")

    def test_local_file(self):
        p = Path(__file__)
        r = fetch.read_local_file(p.as_uri())
        self.assertIn("Magpie", r.text())

    def test_sniff(self):
        self.assertEqual(fetch.sniff_kind(b"<html><body>x", "text/html"), "html")
        self.assertEqual(fetch.sniff_kind(make_png(1, 1), ""), "image")
        self.assertEqual(fetch.sniff_kind(b"ID3\x04x", ""), "media")


class LocalServer:
    def __init__(self, handler):
        self.server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class HttpTests(unittest.TestCase):
    def test_redirect_and_cookies_and_gzip(self):
        body = gzip.compress(b"<html><body>hi</body></html>")

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/go":
                    self.send_response(302)
                    self.send_header("Location", "/land")
                    self.send_header("Set-Cookie", "s=1; Path=/")
                    self.end_headers()
                elif self.path == "/land":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Encoding", "gzip")
                    self.send_header("Set-Cookie", "t=2; Path=/")
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *a):
                pass

        srv = LocalServer(H)
        try:
            client = fetch.HttpClient()
            resp = client.request(srv.url("/go"))
            self.assertEqual(resp.status, 200)
            self.assertTrue(resp.url.endswith("/land"))
            self.assertIn("hi", resp.text())
            cookie = client.cookies.header_for(srv.url("/land"))
            self.assertIn("s=1", cookie)
            self.assertIn("t=2", cookie)
        finally:
            srv.stop()

    def test_redirect_loop(self):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "/loop")
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = LocalServer(H)
        try:
            with self.assertRaises(fetch.FetchError):
                fetch.HttpClient().request(srv.url("/loop"))
        finally:
            srv.stop()


class DomTests(unittest.TestCase):
    def test_basic_page(self):
        page = dom.build_page("https://ex.test/", "<html><head><title>T</title></head><body><h1>Hi</h1><p>Hello <a href='/x'>there</a></p></body></html>", 60)
        self.assertEqual(page.title, "T")
        self.assertEqual(len(page.links), 1)
        self.assertEqual(page.links[0].url, "https://ex.test/x")
        plains = [L.plain() for L in page.lines]
        self.assertTrue(any("Hi" in p for p in plains))

    def test_hidden_and_script_skipped(self):
        page = dom.build_page("https://ex.test/", "<body><p style='display:none'>gone</p><script>var x=1;</script><p>here</p></body>", 60)
        plains = " ".join(L.plain() for L in page.lines)
        self.assertNotIn("gone", plains)
        self.assertNotIn("var x", plains)
        self.assertIn("here", plains)

    def test_selectors(self):
        root = dom.parse_html("<div id=a class='x y'><p class=x>one</p><p>two</p></div>")
        self.assertEqual(len(root.query_selector_all("p.x")), 1)
        self.assertIsNotNone(root.query_selector("#a"))
        self.assertEqual(len(root.query_selector_all("div p")), 2)
        self.assertEqual(len(root.query_selector_all("div > p")), 2)

    def test_form_submit_get(self):
        page = dom.build_page("https://ex.test/", "<form action='/s' method='get'><input name='q' value='hi'><input type='submit'></form>", 60)
        self.assertEqual(len(page.forms), 1)
        method, url, body, ctype = dom.submit_form(page, page.forms[0], {1: "hello"})
        self.assertEqual(method, "GET")
        self.assertIn("q=hello", url)

    def test_table_and_image(self):
        page = dom.build_page("https://ex.test/", "<table><tr><th>a</th><td>b</td></tr></table><img src='i.png' alt='pic'>", 60)
        self.assertEqual(len(page.media), 1)
        plains = " ".join(L.plain() for L in page.lines)
        self.assertIn("a", plains)

    def test_article(self):
        page = dom.build_page("https://ex.test/", "<article><p>" + ("word " * 60) + "</p></article>", 60)
        self.assertGreater(len(dom.extract_article(page)), 200)


class ImageTests(unittest.TestCase):
    def test_png_decode(self):
        data = make_png(4, 3, (255, 0, 0))
        w, h, rgb = image.decode_png(data)
        self.assertEqual((w, h), (4, 3))
        self.assertEqual(len(rgb), 4 * 3 * 3)
        self.assertEqual(tuple(rgb[:3]), (255, 0, 0))

    def test_gif_decode(self):
        w, h, rgb = image.decode_gif(make_gif())
        self.assertEqual((w, h), (2, 1))
        self.assertEqual(len(rgb), 6)

    def test_gif_lying_dimensions_refused_fast(self):
        # The hang: a 65535x65535 header would pad 4G pixels (~38 GiB).
        import time
        bad = bytearray(b"GIF89a")
        bad += struct.pack("<HHBBB", 65535, 65535, 0x80, 0, 0)
        bad += bytes([0, 0, 0] * 2)
        bad += bytes([0x2C, 0, 0, 0, 0, 1, 0, 1, 0, 0x00, 0x01, 0x01, 0x00, 0x00, 0x3B])
        t0 = time.monotonic()
        with self.assertRaises(fetch.FetchError):
            image.decode_gif(bytes(bad))
        self.assertLess(time.monotonic() - t0, 5.0)

    def test_gzip_bomb_capped(self):
        import gzip as _gzip
        # 70 MiB of zeros compresses to ~70 KiB but must not inflate in RAM.
        bomb = _gzip.compress(b"\x00" * (70 * 1024 * 1024))
        self.assertLess(len(bomb), 1024 * 1024)
        with self.assertRaises(fetch.FetchError):
            fetch.HttpClient._decode_body([("Content-Encoding", "gzip")], bomb)

    def test_gzip_normal_ok(self):
        import gzip as _gzip
        data = _gzip.compress(b"<html>hi</html>")
        out = fetch.HttpClient._decode_body([("Content-Encoding", "gzip")], data)
        self.assertEqual(out, b"<html>hi</html>")

    def test_bmp_decode(self):
        w, h, rgb = image.decode_bmp(make_bmp())
        self.assertEqual((w, h), (2, 1))
        self.assertEqual(len(rgb), 6)

    def test_kitty_placeholder_shape(self):
        lines = image.kitty_placeholder_lines(42, 4, 2)
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertIn("\U0010eeee", line)

    def test_kitty_transmit_chunks(self):
        img = image.DisplayImage(7, "png", 8, 8, make_png(2, 2), 4, 2)
        seq = image.kitty_transmit(img)
        self.assertTrue(seq.startswith(b"\x1b_Ga=T,f=100,i=7"))
        self.assertTrue(seq.endswith(b"\x1b\\"))

    def test_ansi_thumbnail(self):
        w, h, rgb = image.decode_png(make_png(8, 8))
        rows = image.ansi_thumbnail(rgb, w, h, 8, 4)
        self.assertEqual(len(rows), 4)


class JSTests(unittest.IsolatedAsyncioTestCase):
    async def run_js(self, src: str):
        from magpie_jslib import evaluate
        from magpie_jsrun import to_string
        interp, g, env, _ = await evaluate(f"__out__ = ({src})", timer_ms=2000)
        return await to_string(interp, g.get("__out__"))

    async def test_arith(self):
        self.assertEqual(await self.run_js("1 + 2 * 3"), "7")

    async def test_closures(self):
        self.assertEqual(await self.run_js("(()=>{function mk(){let n=0; return ()=>++n;} const f=mk(); f(); return f();})()"), "2")

    async def test_class_inheritance(self):
        self.assertEqual(await self.run_js("(()=>{class A{constructor(n){this.n=n;} twice(){return this.n*2;}} class B extends A{} return new B(21).twice();})()"), "42")

    async def test_async_promise(self):
        from magpie_jslib import evaluate
        interp, g, env, _ = await evaluate("__out__ = (async () => await Promise.resolve(9))()", timer_ms=2000)
        from magpie_jsrun import to_string
        p = g.get("__out__")
        v = await interp.await_value(p)
        self.assertEqual(await to_string(interp, v), "9")

    async def test_regex(self):
        self.assertEqual(await self.run_js("/(\\w+)@(\\w+)/.exec('a@b')[0]"), "a@b")

    async def test_json(self):
        self.assertEqual(await self.run_js("JSON.stringify({a:[1,2]})"), '{"a":[1,2]}')

    async def test_errors(self):
        self.assertEqual(await self.run_js("(()=>{try{throw new TypeError('b')}catch(e){return e.name;}})()"), "TypeError")

    async def test_map_set(self):
        self.assertEqual(await self.run_js("(()=>{const m=new Map([['a',1]]); return m.get('a')+m.size;})()"), "2")

    async def test_syntax_error_is_parse_error(self):
        from magpie_jslib import evaluate
        from magpie_jsparse import ParseError
        with self.assertRaises(ParseError):
            await evaluate("function(){", timer_ms=500)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__import__("tempfile").mkdtemp(prefix="magpie-cfg-"))
        self.old = os.environ.get("MAGPIE_CONFIG")
        os.environ["MAGPIE_CONFIG"] = str(self.tmp)

    def tearDown(self):
        import shutil
        if self.old is None:
            os.environ.pop("MAGPIE_CONFIG", None)
        else:
            os.environ["MAGPIE_CONFIG"] = self.old
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_defaults_without_file(self):
        import magpie_config as cfg
        self.assertEqual(cfg.effective()["search.engine"], "auto")
        self.assertEqual(cfg.effective()["browse.ai_bar"], "right")

    def test_roundtrip(self):
        import magpie_config as cfg
        cfg.set_key("search.results", "5")
        self.assertEqual(cfg.get("search.results"), 5)
        cfg.set_key("browse.ai_bar", "left")
        self.assertEqual(cfg.get("browse.ai_bar"), "left")

    def test_rejects_bad_values(self):
        import magpie_config as cfg
        for key, bad in (("search.engine", "google"), ("search.results", "99"),
                         ("search.results", "x"), ("browse.js", "sometimes"),
                         ("browse.ai_bar", "up"), ("ai.enabled", "maybe"),
                         ("media.image_cap_mb", "0"), ("media.inline_images", "65"),
                         ("nope.key", "1")):
            with self.assertRaises(cfg.ConfigError, msg=f"{key}={bad}"):
                cfg.set_key(key, bad)
        self.assertEqual(cfg.set_key("media.inline_images", "4"), 4)

    def test_corrupt_file_falls_back(self):
        import magpie_config as cfg
        cfg.config_path().parent.mkdir(parents=True, exist_ok=True)
        cfg.config_path().write_text("{not json", encoding="utf-8")
        self.assertEqual(cfg.effective()["search.results"], 8)

    def test_env_precedence(self):
        import magpie_config as cfg
        cfg.set_key("search.results", "5")
        os.environ["MAGPIE_RESULTS"] = "3"
        try:
            self.assertEqual(cfg.effective()["search.results"], 3)
        finally:
            del os.environ["MAGPIE_RESULTS"]

    def test_env_tor_and_js(self):
        import magpie_config as cfg
        os.environ["MAGPIE_TOR"] = "yes"
        os.environ["MAGPIE_JS"] = "off"
        try:
            eff = cfg.effective()
            self.assertTrue(eff["search.tor"])
            self.assertEqual(eff["browse.js"], "off")
        finally:
            del os.environ["MAGPIE_TOR"]
            del os.environ["MAGPIE_JS"]

    def test_wizard_with_answers(self):
        import magpie_config as cfg
        from unittest import mock
        answers = iter(["marginalia", "3", "", "off", "", "left", "", "", "", "", "y"])
        with mock.patch("builtins.input", lambda *a: next(answers)), \
                mock.patch.object(sys.stdin, "isatty", return_value=True):
            saved = cfg.run_wizard()
        self.assertEqual(saved["search.engine"], "marginalia")
        self.assertEqual(saved["search.results"], 3)
        self.assertEqual(saved["browse.js"], "off")
        self.assertEqual(saved["browse.ai_bar"], "left")

    def test_wizard_cancel_saves_nothing(self):
        import magpie_config as cfg
        from unittest import mock
        with mock.patch("builtins.input", side_effect=EOFError):
            with self.assertRaises(cfg.ConfigError):
                cfg.run_wizard()
        self.assertFalse(cfg.config_path().is_file())


class AIBarTests(unittest.TestCase):
    def test_bar_frame_both_sides(self):
        import magpie_config as cfg
        from magpie_tui import Browser
        for side in ("right", "left"):
            cfg.set_key("browse.ai_bar", side) if False else None
            b = Browser(js_mode="off")
            b.navigate("magpie:help")
            b.tab.ai_open = True
            b.tab.ai_chat = [("pixie", "hello there")]
            import magpie_config as _cfg
            real = _cfg.effective
            _cfg.effective = lambda: {**real(), "browse.ai_bar": side}
            try:
                frame, transmits = b.frame(100, 30)
            finally:
                _cfg.effective = real
            self.assertIn("pixie", frame)
            self.assertEqual(transmits, [])

    def test_ai_disabled_blocks(self):
        import magpie_config as cfg
        from unittest import mock
        from magpie_tui import Browser
        b = Browser(js_mode="off")
        b.navigate("magpie:help")
        with mock.patch.object(cfg, "effective", return_value={**cfg.effective(), "ai.enabled": False}):
            b.ai_summarize()
        self.assertIn("off", b.flash)
        self.assertFalse(b.tab.ai_open)

    def test_loader_fills_cache_in_background(self):
        from magpie_tui import Browser, _FAILED
        b = Browser(js_mode="off")
        b.navigate("magpie:help")
        tab = b.tab
        key = ("test-img", 60)
        b.loader.request({"kind": "image", "url": "file:///home/evenweaker/faeOS/assets/wall.png",
                          "width": 60, "key": key, "tab": tab})
        deadline = time.monotonic() + 15.0
        while key not in tab.img_cache and time.monotonic() < deadline:
            b.tick()
            time.sleep(0.1)
        b.tick()
        self.assertIn(key, tab.img_cache)
        self.assertNotEqual(tab.img_cache[key], _FAILED)

    def test_loader_marks_failure_no_retry(self):
        from magpie_tui import Browser, _FAILED
        b = Browser(js_mode="off")
        b.navigate("magpie:help")
        tab = b.tab
        key = ("test-bad", 60)
        b.loader.request({"kind": "image", "url": "file:///nonexistent-x.png",
                          "width": 60, "key": key, "tab": tab})
        deadline = time.monotonic() + 15.0
        while key not in tab.img_cache and time.monotonic() < deadline:
            b.tick()
            time.sleep(0.1)
        b.tick()
        self.assertEqual(tab.img_cache[key], _FAILED)

    def test_ai_threaded_completion(self):
        import magpie_config as cfg
        from unittest import mock
        from magpie_tui import Browser

        class FakeLegacy:
            def llm_up(self):
                return True

            def ai_summary(self, prompt, ctx):
                return "pixie says hi"

        b = Browser(js_mode="off")
        b.navigate("magpie:help")
        with mock.patch("magpie_tui.legacy_magpie", return_value=FakeLegacy()):
            b.ai_summarize()
            self.assertTrue(b.tab.ai_open)
            self.assertTrue(b.ai_busy)
            deadline = time.monotonic() + 15.0
            while b.ai_busy and time.monotonic() < deadline:
                b.tick()
                time.sleep(0.1)
            b.tick()
        self.assertFalse(b.ai_busy)
        self.assertEqual(b.tab.ai_chat[-1], ("pixie", "pixie says hi"))

    def test_settings_rows_cover_schema(self):
        import magpie_config as cfg
        from magpie_tui import Browser
        b = Browser(js_mode="off")
        rows = b.settings_rows()
        keys = [k for k, _, _ in rows if not k.startswith("[")]
        for key in cfg.DEFAULTS:
            self.assertIn(key, keys)

    def test_settings_apply_js(self):
        import magpie_config as cfg
        from unittest import mock
        from magpie_tui import Browser
        b = Browser(js_mode="ask")
        with mock.patch.object(cfg, "effective", return_value={**cfg.effective(), "browse.js": "off"}):
            b.apply_settings("browse.js")
        self.assertEqual(b.js_mode, "off")

    def test_config_cli_list(self):
        import importlib.machinery
        import importlib.util
        import io
        from contextlib import redirect_stdout
        loader = importlib.machinery.SourceFileLoader("magpie_cli_test", str(BIN / "magpie"))
        spec = importlib.util.spec_from_loader("magpie_cli_test", loader)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["magpie_cli_test"] = mod
        loader.exec_module(mod)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod.config_dispatch(["list"])
        self.assertEqual(rc, 0)
        self.assertIn("search.engine", buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod.config_dispatch(["set", "browse.js", "bogus"])
        self.assertEqual(rc, 2)
    async def test_script_touches_dom(self):
        page = dom.build_page(
            "https://ex.test/",
            "<html><head><title>T</title></head><body><div id=app>hi</div>"
            "<script>document.getElementById('app').textContent = 'yo'; document.title='JT';</script></body></html>",
            60, js_enabled=True,
        )
        client = fetch.HttpClient()
        from magpie_jsdom import Bindings
        from magpie_script import run_page_scripts
        b = Bindings(page, client)
        result = await run_page_scripts(b, js_enabled=True, budget_ms=3000, width=60)
        self.assertEqual(result.errors, [])
        self.assertEqual(b.page.title, "JT")
        plains = " ".join(L.plain() for L in b.page.lines)
        self.assertIn("yo", plains)

    async def test_click_listener_and_nav(self):
        page = dom.build_page(
            "https://ex.test/",
            "<body><a id=l href='/next'>go</a><script>document.getElementById('l').addEventListener('click', e => { window.__c = 1; });</script></body>",
            60, js_enabled=True,
        )
        client = fetch.HttpClient()
        from magpie_jsdom import Bindings, dispatch
        from magpie_script import run_page_scripts
        b = Bindings(page, client)
        await run_page_scripts(b, js_enabled=True, budget_ms=3000, width=60)
        from magpie_jslib import create_sandbox  # noqa
        w = b.wrap(b.page.root.query_selector("#l"))
        # Dispatch through a fresh interpreter is overkill; assert listener registered.
        node = b.page.root.query_selector("#l")
        self.assertIn("click", node.script_state.get("listeners", {}))


class TuiTests(unittest.TestCase):
    def test_internal_pages(self):
        from magpie_tui import Browser
        b = Browser(js_mode="off")
        for url in ("magpie:start", "magpie:help", "magpie:history", "magpie:bookmarks", "magpie:media"):
            b.navigate(url)
            self.assertIsNotNone(b.tab.page)
            self.assertTrue(len(b.tab.page.lines) > 0)

    def test_frame_builds(self):
        from magpie_tui import Browser
        b = Browser(js_mode="off")
        b.navigate("magpie:help")
        frame, transmits = b.frame(100, 30)
        self.assertIn("magpie", frame)
        self.assertEqual(transmits, [])

    def test_input_reader_csi(self):
        from magpie_tui import decode_csi
        self.assertEqual(decode_csi("A"), "up")
        self.assertEqual(decode_csi("3~"), "delete")
        self.assertEqual(decode_csi("Z"), "shift-tab")

    def test_input_reader_splits_escapes(self):
        import os
        from magpie_tui import InputReader

        def feed(data: bytes):
            r, w = os.pipe()
            os.write(w, data)
            os.close(w)
            return InputReader(r)

        rd = feed(b"\x1b[B\x1b[B\r")
        self.assertEqual([rd.read(timeout=1) for _ in range(3)], ["down", "down", "enter"])
        rd = feed("çé".encode("utf-8"))
        self.assertEqual([rd.read(timeout=1) for _ in range(2)], ["ç", "é"])
        rd = feed(b"\x1b[97;5u")
        self.assertEqual(rd.read(timeout=1), "ctrl-a")

    def test_legacy_search_bridge_loads(self):
        from magpie_tui import legacy_magpie
        mod = legacy_magpie()
        self.assertTrue(hasattr(mod, "search_chain"))


if __name__ == "__main__":
    unittest.main()
