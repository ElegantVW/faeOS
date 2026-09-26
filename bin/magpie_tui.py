#!/usr/bin/env python3
"""magpie_tui — the Magpie browse TUI: tabs, address bar, pink chrome.

Own input layer (UTF-8 aware, so PT keyboards type ç/ã/õ everywhere),
native Kitty image placement inside the page box, ANSI fallback elsewhere,
and workloads delegated to magpie_fetch/dom/image/script. No TUI toolkit,
no browser engine borrowed: just fae_termart frames and our own code.
"""
from __future__ import annotations

import importlib.util
import os
import queue
import re
import select
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.expanduser("~/bin"))
try:
    import fae_termart as art
except ImportError:
    print("magpie browse: cannot import fae_termart (deploy it to ~/bin)", file=sys.stderr)
    raise SystemExit(1)

from magpie_dom import (
    CSSColor, Line, Page, Segment, build_page, extract_article, find_text_rows,
    layout_dom, submit_form,
)
from magpie_fetch import (
    FetchError, HttpClient, Response, bookmarks_path, cache_media_bytes,
    clear_history, config_dir, download_to_downloads, ensure_dirs,
    history_path, import_lynx_bookmarks, load_bookmarks, load_history,
    normalize_url, parse_data_url, read_local_file, record_history,
    resolve_url, safe_filename, save_bookmarks, sniff_kind, url_host_label,
)
from magpie_image import (
    DisplayImage, MediaPlayer, ansi_thumbnail, check_media_backends,
    decode_bmp, decode_gif, decode_png, detect_format, fit_cells,
    image_dimensions, kitty_delete, kitty_placeholder_lines, kitty_terminal,
    kitty_transmit, prepare_display_image, rasterize_with_ffmpeg,
    truecolor_terminal, video_thumbnail,
)

P = art.P
os.environ.setdefault("PIXIE_UNICODE", "1")

LEGACY = None

# Cache sentinel: a fetch that failed stays failed (no per-frame retries).
_FAILED = {"kind": "failed"}

# Cache lookup sentinel: distinguishes "never tried" from "tried, failed".
_MISSING = object()


class MediaLoader:
    """Background image/poster fetcher so the render path never blocks.

    Tasks carry a generation number; cancel() bumps it and drops everything
    queued or stale. Results land on `done` for tick() to shelve into tabs.
    """

    def __init__(self, browser) -> None:
        self.browser = browser
        self.tasks: queue.Queue = queue.Queue()
        self.done: queue.Queue = queue.Queue()
        self.generation = 0
        self._gen_lock = threading.Lock()
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()

    def request(self, task: dict) -> None:
        with self._gen_lock:
            task["gen"] = self.generation
        self.tasks.put(task)

    def cancel(self) -> None:
        with self._gen_lock:
            self.generation += 1
        try:
            while True:
                self.tasks.get_nowait()
        except queue.Empty:
            pass

    def _work(self) -> None:
        while True:
            task = self.tasks.get()
            try:
                with self._gen_lock:
                    current = self.generation
                if task.get("gen") != current:
                    continue
                browser = self.browser
                if task["kind"] == "image":
                    result = browser.load_image_data(task["url"], task["width"])
                else:
                    result = browser.load_poster_data(task["url"], task["width"])
                with self._gen_lock:
                    fresh = task.get("gen") == self.generation
                if fresh:
                    self.done.put((task, result if result is not None else _FAILED))
            except Exception:
                try:
                    self.done.put((task, _FAILED))
                except queue.Full:
                    pass


def legacy_magpie():
    """Load the classic search/AI half of magpie (same directory, no import)."""
    global LEGACY
    if LEGACY is not None:
        return LEGACY
    path = Path(__file__).with_name("magpie")
    if not path.is_file():
        path = Path.home() / "bin" / "magpie"
    import importlib.machinery
    loader = importlib.machinery.SourceFileLoader("magpie_legacy", str(path))
    spec = importlib.util.spec_from_loader("magpie_legacy", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["magpie_legacy"] = mod
    loader.exec_module(mod)
    LEGACY = mod
    return mod


# ── UTF-8 input ──────────────────────────────────────────────────────────

CSI_MAP = {
    "A": "up", "B": "down", "C": "right", "D": "left", "Z": "shift-tab",
    "H": "home", "F": "end",
}


def decode_csi(body: str) -> str:
    if not body:
        return "esc"
    if body[0] in CSI_MAP and (len(body) == 1 or body[1] == ";"):
        base = CSI_MAP[body[0]]
        mods = ""
        if ";" in body:
            try:
                mods = body.split(";")[1].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz~")
            except (ValueError, IndexError):
                mods = ""
        return base
    if body in ("1~", "7~", "H"):
        return "home"
    if body in ("4~", "8~", "F"):
        return "end"
    if body == "3~":
        return "delete"
    if body == "5~":
        return "pgup"
    if body == "6~":
        return "pgdn"
    if body == "Z":
        return "shift-tab"
    # Kitty keyboard protocol: CSI unicode ; mods u
    m = re.fullmatch(r"(\d+)(?::(\d+))?(?::(\d+))?;(\d+)(?::(\d+))?u", body)
    if m:
        code = int(m.group(1))
        mods = int(m.group(4)) - 1
        names = {13: "enter", 9: "tab", 27: "esc", 32: "space", 127: "backspace"}
        if code in names:
            base = names[code]
        elif 32 <= code < 127:
            ch = chr(code)
            if mods & 4 and ch.isalpha():
                base = f"ctrl-{ch.lower()}"
            else:
                base = ch.upper() if mods & 1 and ch.isalpha() else ch
        else:
            base = f"key-{code}"
        if mods & 2 and base not in ("esc",):
            base = "alt-" + base
        return base
    # Legacy modifiers: CSI 1 ; mods A (arrows etc.)
    m = re.fullmatch(r"1;(\d+)([ABCD])", body)
    if m:
        return CSI_MAP.get(m.group(2), "esc")
    return f"csi:{body}"


def decode_byte(ch: bytes):
    if ch in (b"\r", b"\n"):
        return "enter"
    if ch == b" ":
        return "space"
    if ch == b"\t":
        return "tab"
    if ch == b"\x03":
        return "ctrl-c"
    if ch == b"\x04":
        return "ctrl-d"
    if ch in (b"\x7f", b"\x08"):
        return "backspace"
    if ch == b"\x15":
        return "ctrl-u"
    if ch == b"\x12":
        return "ctrl-r"
    if ch == b"\x13":
        return "ctrl-s"
    if ch == b"\x17":
        return "ctrl-w"
    if ch == b"\x01":
        return "ctrl-a"
    if ch == b"\x05":
        return "ctrl-e"
    if ch == b"\x10":
        return "ctrl-p"
    if ch == b"\x0c":
        return "ctrl-l"
    if ch == b"\x16":
        return "ctrl-v"
    if ch == b"\x19":
        return "ctrl-y"
    if ch == b"\x0b":
        return "ctrl-k"
    if ch == b"\x0e":
        return "ctrl-n"
    if ch == b"\x14":
        return "ctrl-t"
    return None


class InputReader:
    """Byte input with UTF-8 reassembly, CSI/SS3/mouse parsing, paste queue.

    A persistent raw buffer means back-to-back escape sequences in one
    os.read() are split into separate events instead of being glued into
    one bogus CSI body.
    """

    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.pending: list = []
        self.raw = bytearray()

    def read(self, timeout: float | None = None):
        if self.pending:
            return self.pending.pop(0)
        if not self.raw:
            r, _, _ = select.select([self.fd], [], [], timeout)
            if not r:
                return ""
            try:
                data = os.read(self.fd, 256)
            except OSError:
                return "esc"
            if not data:
                return "esc"
            self.raw += data
        return self._parse_one()

    def _more(self, timeout: float = 0.05) -> bool:
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return False
        try:
            data = os.read(self.fd, 256)
        except OSError:
            return False
        if data:
            self.raw += data
        return bool(data)

    def _parse_one(self):
        if not self.raw:
            return ""
        if self.raw[0] == 0x1B:
            if len(self.raw) == 1:
                if not self._more():
                    self.raw.clear()
                    return "esc"
            if len(self.raw) > 1 and self.raw[1:2] == b"[":
                # First final byte in 0x40..0x7E ends THIS sequence.
                end = None
                for k in range(2, min(len(self.raw), 40)):
                    if 0x40 <= self.raw[k] <= 0x7E:
                        end = k
                        break
                if end is None:
                    if len(self.raw) < 40 and self._more():
                        return self._parse_one()
                    del self.raw[:2]
                    return "esc"
                body = bytes(self.raw[2:end + 1]).decode("latin-1")
                del self.raw[:end + 1]
                if body.startswith("<"):
                    me = art.parse_sgr_mouse(body)
                    if me is not None:
                        return me
                return decode_csi(body)
            if len(self.raw) > 1 and self.raw[1:2] == b"O":
                if len(self.raw) < 3:
                    if not self._more():
                        del self.raw[:2]
                        return "esc"
                    return self._parse_one()
                ch = chr(self.raw[2])
                del self.raw[:3]
                return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(ch, "esc")
            if len(self.raw) > 1 and self.raw[1:2] == b"\x1b":
                del self.raw[:1]
                return "esc"
            # Alt+key: ESC plus one complete UTF-8 char.
            for n in (1, 2, 3, 4):
                if len(self.raw) < 1 + n:
                    if not self._more():
                        break
                    continue
                try:
                    ch = bytes(self.raw[1:1 + n]).decode("utf-8")
                except UnicodeDecodeError:
                    continue
                del self.raw[:1 + n]
                return "alt-" + ch
            del self.raw[:1]
            return "esc"
        # UTF-8 text (possibly a paste burst): decode the complete prefix,
        # keep any partial tail for the next read.
        for end in range(len(self.raw), 0, -1):
            try:
                text = bytes(self.raw[:end]).decode("utf-8")
                break
            except UnicodeDecodeError:
                continue
        else:
            if len(self.raw) > 6:
                self.raw.clear()
                return ""
            self._more()
            return self._parse_one()
        del self.raw[:end]
        if not text:
            return ""
        if len(text) == 1:
            ch = text
            if ch in ("\r", "\n"):
                return "enter"
            if ch == " ":
                return "space"
            if ch == "\t":
                return "tab"
            if ord(ch) < 32 or ord(ch) == 0x7F:
                key = decode_byte(ch.encode("latin-1"))
                return key if key is not None else ""
            return ch
        for ch in text:
            if ch in ("\r", "\n"):
                self.pending.append("enter")
            elif ch == "\t":
                self.pending.append("tab")
            elif ord(ch) < 32 or ord(ch) == 0x7F:
                key = decode_byte(ch.encode("latin-1"))
                if key is not None:
                    self.pending.append(key)
            elif ch.isprintable() or ch == " ":
                self.pending.append(ch)
        return self.pending.pop(0) if self.pending else ""


# ── tabs & pages ─────────────────────────────────────────────────────────

@dataclass
class Tab:
    url: str = "magpie:start"
    title: str = "start"
    page: Page | None = None
    bindings: object | None = None
    scroll: int = 0
    focus: int = 0
    history: list[str] = field(default_factory=list)
    hindex: int = -1
    form_state: dict = field(default_factory=dict)
    img_ids: list[int] = field(default_factory=list)
    img_cache: dict = field(default_factory=dict)
    reader: bool = False
    find: str = ""
    find_rows: list[int] = field(default_factory=list)
    find_idx: int = -1
    status: str = ""
    js_badge: str = ""
    layout_w: int = 80
    _file_response: object = None
    ai_open: bool = False
    ai_typing: bool = False
    ai_buf: str = ""
    ai_chat: list = field(default_factory=list)  # [(role, text)]
    ai_scroll: int = 0
    img_pending: set = field(default_factory=set)  # cache keys with a load in flight


class Browser:
    def __init__(self, *, tor: bool = False, js_mode: str = "ask") -> None:
        ensure_dirs()
        self.client = HttpClient(tor=tor, timeout=25.0)
        self.tor = tor
        self.js_mode = js_mode  # on | off | ask
        self.js_allow: set[str] = set()
        self.js_deny: set[str] = set()
        self.tabs: list[Tab] = [Tab()]
        self.cur = 0
        self.player = MediaPlayer()
        self.flash = ""
        self.mode = "browse"
        self.overlay_rows: list[str] = []
        self.overlay_title = ""
        self.overlay_actions: list = []
        self.overlay_sel = 0
        self.addr_buf = ""
        self.find_buf = ""
        self.field_edit: tuple | None = None
        self.edit_buf = ""
        self.next_image_id = 1
        self.truecolor = truecolor_terminal()
        self.kitty = kitty_terminal()
        self.pending_transmits: list[bytes] = []
        self.tor_locked = False
        self.js_locked = False
        self.settings_sel = 0
        self.settings_buf = ""
        self.settings_edit_key_name = ""
        self._model_state = "asleep"
        self._model_checked = 0.0
        self._id_lock = threading.Lock()
        self.loader = MediaLoader(self)
        self.ai_done: queue.Queue = queue.Queue()
        self.ai_busy = False
        self.ai_gen = 0

    @property
    def tab(self) -> Tab:
        return self.tabs[self.cur]

    def content_width(self) -> int:
        return max(40, min(art.term_width(), 110) - 4)

    # ── navigation ──
    def navigate(self, url: str, *, push: bool = True, referrer: str = "") -> None:
        tab = self.tab
        tab._file_response = None
        tab.img_pending.clear()
        self.loader.cancel()
        tab.layout_w = self.content_width()
        url = url.strip()
        if not url:
            return
        if url.startswith("magpie:"):
            self.open_internal(url, push=push)
            return
        try:
            url = normalize_url(url, base=tab.url if tab.url.startswith("http") else None)
        except FetchError:
            self.search(url)
            return
        scheme = urllib.parse.urlparse(url).scheme.lower()
        if scheme == "file":
            try:
                resp = read_local_file(url)
            except FetchError as e:
                self.fail(str(e))
                return
            self.show_response(url, resp, push=push)
            return
        if scheme == "data":
            try:
                resp = parse_data_url(url)
            except FetchError as e:
                self.fail(str(e))
                return
            self.show_response(url, resp, push=push)
            return
        if scheme not in ("http", "https"):
            self.fail(f"magpie cannot open {scheme or '(no scheme)'} addresses")
            return
        self.status(f"fetching {url_host_label(url)}…")
        self.paint_status_only()
        try:
            resp = self.client.request(url, top_level=True, site_hint=referrer)
        except FetchError as e:
            self.fail(str(e))
            return
        self.show_response(url, resp, push=push, referrer=referrer)

    def show_response(self, url: str, resp: Response, *, push: bool = True, referrer: str = "") -> None:
        tab = self.tab
        kind = sniff_kind(resp.data, resp.content_type)
        if resp.status >= 400 and kind not in ("html", "text"):
            self.fail(f"{url_host_label(url) or 'the page'} answered HTTP {resp.status}")
            return
        if kind == "html" or (kind == "text" and resp.is_text() and len(resp.data) < 200000):
            self.show_html(resp.url, resp, push=push, referrer=referrer)
        elif kind == "image":
            self.show_media_page(resp.url, resp, "image", push=push)
        elif kind == "media":
            self.show_media_page(resp.url, resp, "media", push=push)
        elif kind == "text":
            self.show_text_page(resp.url, resp, push=push)
        else:
            self.show_file_page(resp.url, resp, push=push)

    def show_html(self, url: str, resp: Response, *, push: bool, referrer: str = "") -> None:
        from magpie_jsdom import Bindings
        tab = self.tab
        width = tab.layout_w
        js = self.js_for(url)
        try:
            page = build_page(url, resp.text(), width, js_enabled=js)
        except (ValueError, MemoryError, RecursionError) as e:
            self.fail(f"the page would not parse ({e})")
            return
        bindings = Bindings(page, self.client, term_size=(art.term_width(), art.term_height()))
        bindings.referrer = referrer
        tab.bindings = bindings
        tab.page = page
        if js and page.scripts:
            tab.js_badge = f"JS ran: {len(page.scripts)} script(s)"
            self.status("pixie is waking the page scripts…")
            self.paint_status_only()
            try:
                import asyncio
                from magpie_script import run_page_scripts
                result = asyncio.run(run_page_scripts(bindings, js_enabled=True, width=width))
                tab.js_badge = f"JS: {result.ran} ran · {len(result.errors)} grumble(s)"
                for err in result.errors[:3]:
                    tab.js_badge += f" · {err[:60]}"
                page = bindings.page
                tab.page = page
            except (RuntimeError, OSError, ValueError) as e:
                tab.js_badge = f"JS stumbled: {e}"
        elif page.scripts and not js:
            tab.js_badge = f"JS held: {len(page.scripts)} script(s) quiet (J to allow)"
        else:
            tab.js_badge = ""
        tab.url = page.url
        tab.title = page.title or url_host_label(url)
        tab.scroll = 0
        tab.focus = 0
        tab.reader = False
        tab.img_cache = {}
        self.clear_images(tab)
        if push:
            tab.history = tab.history[: tab.hindex + 1] + [page.url]
            tab.hindex += 1
        bindings.history_stack = list(tab.history) or [page.url]
        bindings.history_index = tab.hindex if tab.hindex >= 0 else 0
        record_history(page.url, tab.title)
        self.handle_nav_requests(tab)
        self.flash = ""

    def handle_nav_requests(self, tab: Tab) -> None:
        bindings = tab.bindings
        if bindings is None:
            return
        if bindings.nav_request:
            url, replace = bindings.nav_request
            bindings.nav_request = None
            self.navigate(url, push=not replace)
            return
        if bindings.open_request:
            url = bindings.open_request
            bindings.open_request = None
            self.new_tab(url)
            return
        if bindings.submit_request is not None:
            form = bindings.submit_request
            bindings.submit_request = None
            self.submit_form(tab, form)
            return
        if bindings.media_request is not None:
            action, src = bindings.media_request
            bindings.media_request = None
            if action == "play":
                self.play_url(src)
            return
        if bindings.pending_scroll is not None:
            kind, val = bindings.pending_scroll
            bindings.pending_scroll = None
            if kind == "anchor" and val in (tab.page.anchors if tab.page else {}):
                tab.scroll = max(0, tab.page.anchors[val] - 2)
            elif kind == "top":
                tab.scroll = 0

    def js_for(self, url: str) -> bool:
        if self.js_mode == "on":
            return True
        if self.js_mode == "off":
            return False
        host = url_host_label(url)
        if host in self.js_allow:
            return True
        if host in self.js_deny or not host:
            return False
        # Ask once per host per session.
        answer = self.ask(f"let {host or url} run scripts?  (y = this visit · a = always · n = hold)", ["y", "a", "n"])
        if answer == "a":
            self.js_allow.add(host)
            return True
        if answer == "y":
            return True
        self.js_deny.add(host)
        return False

    def show_text_page(self, url: str, resp: Response, *, push: bool) -> None:
        tab = self.tab
        text = resp.text()
        html = "<html><head><title>{}</title></head><body><pre>{}</pre></body></html>".format(
            _escape(url_host_label(url) or url),
            _escape(text[:60000]),
        )
        page = build_page(url, html, tab.layout_w)
        tab.page = page
        tab.bindings = None
        tab.url = url
        tab.title = url_host_label(url) or "text"
        tab.scroll = 0
        tab.focus = 0
        if push:
            tab.history = tab.history[: tab.hindex + 1] + [url]
            tab.hindex += 1
        record_history(url, tab.title)

    def show_media_page(self, url: str, resp: Response, kind: str, *, push: bool) -> None:
        tab = self.tab
        suffix = _suffix_for(resp)
        try:
            path = cache_media_bytes(resp.data, suffix)
        except OSError as e:
            self.fail(f"could not cache media ({e})")
            return
        label = "image" if kind == "image" else "media"
        html = (
            f"<html><head><title>{_escape(path.name)}</title></head><body>"
            f"<h1>{label}: {_escape(path.name)}</h1>"
            f"<p>{len(resp.data) // 1024} KiB · {_escape(resp.content_type or 'unknown type')}</p>"
            + (f'<img src="file://{path}" alt="{_escape(path.name)}">' if kind == "image" else
               f'<video src="{_escape(url)}"></video>')
            + "<p>keys: v play · d download · i fullscreen (images) · q back</p>"
            + "</body></html>"
        )
        page = build_page(url, html, tab.layout_w)
        tab.page = page
        tab.bindings = None
        tab.url = url
        tab.title = path.name
        tab.scroll = 0
        tab.focus = 0
        if push:
            tab.history = tab.history[: tab.hindex + 1] + [url]
            tab.hindex += 1
        record_history(url, tab.title)

    def show_file_page(self, url: str, resp: Response, *, push: bool) -> None:
        name = safe_filename(url, resp.content_type, resp.header("Content-Disposition"))
        html = (
            f"<html><head><title>{_escape(name)}</title></head><body>"
            f"<h1>file: {_escape(name)}</h1>"
            f"<p>{len(resp.data) // 1024} KiB · {_escape(resp.content_type or 'unknown type')}</p>"
            "<p>keys: d download to ~/Downloads · q back</p>"
            "</body></html>"
        )
        page = build_page(url, html, tab.layout_w)
        tab.page = page
        tab.bindings = None
        tab.url = url
        tab.title = name
        tab.scroll = 0
        tab.focus = 0
        tab._file_response = resp
        if push:
            tab.history = tab.history[: tab.hindex + 1] + [url]
            tab.hindex += 1

    # ── internal pages ──
    def open_internal(self, url: str, *, push: bool = True) -> None:
        tab = self.tab
        if url.startswith("magpie:search?"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
            self.search(q)
            return
        builders = {
            "magpie:start": self.start_html,
            "magpie:help": self.help_html,
            "magpie:history": self.history_html,
            "magpie:bookmarks": self.bookmarks_html,
            "magpie:media": self.media_html,
            "magpie:downloads": self.downloads_html,
        }
        builder = builders.get(url.split("?")[0])
        if builder is None:
            self.fail(f"unknown magpie: page {url}")
            return
        page = build_page(url, builder(), tab.layout_w)
        tab.page = page
        tab.bindings = None
        tab.url = url
        tab.title = url.split(":")[1]
        tab.scroll = 0
        tab.focus = 0
        if push:
            tab.history = tab.history[: tab.hindex + 1] + [url]
            tab.hindex += 1

    def start_html(self) -> str:
        marks = load_bookmarks()[:12]
        hist = load_history(8)
        rows = ["<html><head><title>start</title></head><body><h1>magpie den</h1>"]
        rows.append("<p>o address · bare words search the quiet web · ? keys · J scripts</p>")
        if marks:
            rows.append("<h2>bookmarks</h2><ul>")
            for m in marks:
                rows.append(f'<li><a href="{_escape(m["url"])}">{_escape(m["title"])}</a></li>')
            rows.append("</ul>")
        if hist:
            rows.append("<h2>recent</h2><ul>")
            for h in hist:
                rows.append(f'<li><a href="{_escape(h.url)}">{_escape(h.title or h.url)}</a></li>')
            rows.append("</ul>")
        rows.append("</body></html>")
        return "".join(rows)

    def help_html(self) -> str:
        keys = [
            ("o", "address bar (URL or search words)"), ("j/k · Tab", "hop between links & buttons"),
            ("↑↓ · pgup/dn · space", "scroll"), ("enter", "open focused link / press button"),
            ("b / F", "back / forward"), ("r", "reload"), ("H / B / M", "history · bookmarks · media"),
            ("m", "bookmark this page"), ("J", "scripts on/off/ask"), ("R", "reader (article text)"),
            ("a", "ask Pixie about this page"), ("A", "toggle Pixie bar"), (";", "settings"),
            ("v / i / d", "play · fullscreen · download media"),
            ("e", "open in zen (full engine)"), ("y", "copy address (OSC52)"),
            ("t / W / { / }", "new tab · close tab · prev/next tab"), ("/ + n/N", "find in page"),
            ("s", "save page text"), ("q", "close tab / quit"),
        ]
        rows = ["<html><head><title>keys</title></head><body><h1>magpie keys</h1><ul>"]
        for k, v in keys:
            rows.append(f"<li><b>{k}</b> — {v}</li>")
        rows.append("</ul></body></html>")
        return "".join(rows)

    def history_html(self) -> str:
        rows = ["<html><head><title>history</title></head><body><h1>history</h1><p>C clears it</p><ul>"]
        for h in load_history(60):
            rows.append(f'<li><a href="{_escape(h.url)}">{_escape(h.title or h.url)}</a></li>')
        rows.append("</ul></body></html>")
        return "".join(rows)

    def bookmarks_html(self) -> str:
        rows = ["<html><head><title>bookmarks</title></head><body><h1>bookmarks</h1><p>m bookmarks this page · L imports lynx</p><ul>"]
        for m in load_bookmarks():
            rows.append(f'<li><a href="{_escape(m["url"])}">{_escape(m["title"])}</a></li>')
        rows.append("</ul></body></html>")
        return "".join(rows)

    def media_html(self) -> str:
        tab = self.tab
        rows = ["<html><head><title>media</title></head><body><h1>media on this page</h1>"]
        if not tab.page or not tab.page.media:
            rows.append("<p>no pictures or players here.</p>")
        else:
            rows.append("<ul>")
            for m in tab.page.media:
                rows.append(f'<li>[{m.kind} {m.ident}] <a href="{_escape(m.url)}">{_escape(m.alt or m.title or m.url[:80])}</a></li>')
            rows.append("</ul>")
        rows.append("</body></html>")
        return "".join(rows)

    def downloads_html(self) -> str:
        rows = ["<html><head><title>downloads</title></head><body><h1>downloads</h1><ul>"]
        dl = sorted((Path.home() / "Downloads").glob("magpie-*"))[-20:] if (Path.home() / "Downloads").is_dir() else []
        for p in dl:
            rows.append(f"<li>{_escape(p.name)}</li>")
        rows.append("</ul></body></html>")
        return "".join(rows)

    # ── search ──
    def search(self, query: str) -> None:
        query = query.strip()
        if not query:
            return
        try:
            legacy = legacy_magpie()
        except (ImportError, OSError) as e:
            self.fail(f"search half missing ({e})")
            return
        self.status(f"asking the quiet web about {query[:60]}…")
        self.paint_status_only()
        try:
            results, eng, err = legacy.search_chain(query, n=10, tor=self.tor, page=1)
        except (ValueError, RuntimeError, OSError) as e:
            self.fail(f"search stumbled ({e})")
            return
        if not results:
            self.fail(err or "no results from the quiet web")
            return
        rows = [f"<html><head><title>{_escape(query)}</title></head><body><h1>{_escape(query)}</h1><p>via {_escape(eng)}</p><ul>"]
        for r in results:
            title = _escape((r.get("title") or "(no title)").strip())
            url = _escape(r.get("url") or "")
            snip = _escape((r.get("abstract") or "")[:280])
            if url:
                rows.append(f'<li><a href="{url}">{title}</a><br>{snip}</li>')
        rows.append("</ul></body></html>")
        tab = self.tab
        page = build_page(f"magpie:search?q={urllib.parse.quote(query)}", "".join(rows), tab.layout_w)
        tab.page = page
        tab.bindings = None
        tab.url = page.url
        tab.title = f"search: {query[:40]}"
        tab.scroll = 0
        tab.focus = 0
        tab.history = tab.history[: tab.hindex + 1] + [page.url]
        tab.hindex += 1
        self.flash = ""

    # ── actions ──
    def fail(self, msg: str) -> None:
        self.flash = msg

    def status(self, msg: str) -> None:
        self.flash = msg

    def ask(self, prompt: str, options: list[str]) -> str:
        # Modal ask rendered by the frame loop; blocks on keys.
        self.mode = "ask"
        self.ask_prompt = prompt
        self.ask_options = options
        self.paint()
        answer = ""
        while True:
            ev = self.reader.read(timeout=60)
            if isinstance(ev, str) and ev.lower() in options:
                answer = ev.lower()
                break
            if ev in ("esc", "q", "ctrl-c", ""):
                answer = options[-1]
                break
        self.mode = "browse"
        return answer

    def submit_form(self, tab: Tab, form) -> None:
        state = {}
        for fid in form.fields:
            fld = next((f for f in tab.page.fields if f.ident == fid), None)
            if fld is None:
                continue
            state[fid] = tab.form_state.get(fid, fld.value if not fld.kind == "checkbox" else fld.checked)
        try:
            method, url, body, ctype = submit_form(tab.page, form, state)
        except (ValueError, KeyError) as e:
            self.fail(f"the form would not pack ({e})")
            return
        if method == "GET":
            self.navigate(url)
            return
        try:
            resp = self.client.request(url, method="POST", body=body, content_type=ctype, top_level=True)
        except FetchError as e:
            self.fail(str(e))
            return
        self.show_response(url, resp, push=True)

    def play_url(self, url: str) -> None:
        try:
            self.flash = self.player.play(url, kind="video", title=url_host_label(url) or url)
        except FetchError as e:
            self.fail(str(e))

    def download_focused(self) -> None:
        tab = self.tab
        if tab.page is None:
            return
        focus = self.focused_target()
        if focus is None:
            # Whole-page file response?
            resp = getattr(tab, "_file_response", None)
            if resp is not None:
                try:
                    dest = download_to_downloads(resp)
                    self.flash = f"saved {dest.name}"
                except FetchError as e:
                    self.fail(str(e))
                return
            self.fail("nothing downloadable under the cursor")
            return
        kind, ident = focus
        if kind == "media":
            m = tab.page.media[ident - 1]
            try:
                resp = self.client.request(m.url, top_level=False)
            except FetchError as e:
                self.fail(str(e))
                return
            try:
                dest = download_to_downloads(resp)
                self.flash = f"saved {dest.name}"
            except FetchError as e:
                self.fail(str(e))
        elif kind == "link":
            self.navigate(tab.page.links[ident - 1].url)

    def new_tab(self, url: str = "magpie:start") -> None:
        self.tabs.append(Tab())
        self.cur = len(self.tabs) - 1
        self.navigate(url, push=True)

    def close_tab(self) -> None:
        if len(self.tabs) > 1:
            self.clear_images(self.tab)
            del self.tabs[self.cur]
            self.cur = max(0, min(self.cur, len(self.tabs) - 1))
        else:
            raise SystemExit(0)

    def clear_images(self, tab: Tab) -> None:
        if self.kitty and tab.img_ids and hasattr(self, "fd"):
            try:
                for iid in tab.img_ids:
                    os.write(self.fd, kitty_delete(iid))
            except OSError:
                pass
        tab.img_ids = []

    # ── focus model ──
    def focusables(self) -> list[tuple[str, int]]:
        tab = self.tab
        if tab.page is None:
            return []
        out: list[tuple[str, int]] = []
        for i, line in enumerate(tab.page.lines):
            for lid in line.links:
                out.append(("link", lid))
            for mid in line.medias:
                out.append(("media", mid))
            for fid in line.fields:
                out.append(("field", fid))
        # De-duplicate consecutive repeats from wrapped rows.
        dedup: list[tuple[str, int]] = []
        for item in out:
            if not dedup or dedup[-1] != item:
                dedup.append(item)
        return dedup

    def focused_target(self) -> tuple[str, int] | None:
        items = self.focusables()
        if not items:
            return None
        tab = self.tab
        tab.focus = max(0, min(tab.focus, len(items) - 1))
        return items[tab.focus]

    def focus_row(self) -> int:
        tab = self.tab
        target = self.focused_target()
        if target is None or tab.page is None:
            return 0
        kind, ident = target
        for i, line in enumerate(tab.page.lines):
            if (kind == "link" and ident in line.links) or (kind == "media" and ident in line.medias) or (kind == "field" and ident in line.fields):
                return i
        return 0

    def ensure_focus_visible(self, body_h: int) -> None:
        tab = self.tab
        row = self.focus_row()
        if row < tab.scroll:
            tab.scroll = row
        elif row >= tab.scroll + body_h:
            tab.scroll = max(0, row - body_h + 1)

    # ── frame ──
    def paint(self) -> None:
        fd = self.fd
        tw = art.term_width()
        th = art.term_height()
        self.relayout_if_resized(tw)
        frame, transmits = self.frame(tw, th)
        try:
            art.paint_frame(fd, frame)
            for chunk in transmits:
                try:
                    os.write(fd, chunk)
                except OSError:
                    break
        except OSError:
            pass

    def relayout_if_resized(self, tw: int) -> None:
        tab = self.tab
        width = max(40, min(tw, 110) - 4)
        if tab.page is None or width == tab.layout_w:
            return
        try:
            tab.layout_w = width
            tab.page = layout_dom(tab.page.root, tab.page.url, width, js_enabled=False, title_override=tab.page.title)
            tab.img_cache = {}
            self.clear_images(tab)
        except (ValueError, MemoryError, RecursionError):
            pass

    def paint_status_only(self) -> None:
        if not hasattr(self, "fd"):
            return
        try:
            cols = art.term_width()
            msg = art.pad_vis("  " + (self.flash or "…"), max(8, cols - 4))
            art.tty_write(self.fd, f"\x1b[{art.term_height()};1H" + art.paint(msg, P.MUTED) + "\x1b[K")
        except OSError:
            pass

    def frame(self, tw: int, th: int) -> tuple[str, list[bytes]]:
        tab = self.tab
        outer = max(36, min(tw, 110))
        head = self.header_lines(outer)
        runes = self.runes_lines(outer)
        head_h = len(head)
        runes_h = len(runes)
        body_h = max(3, th - head_h - runes_h - 2)
        if tab.ai_open and self.mode not in ("overlay", "settings", "settings_edit"):
            import magpie_config as cfg
            side = str(cfg.effective().get("browse.ai_bar", "right"))
            bar_w = min(46, max(28, outer * 38 // 100))
            page_w = max(20, outer - bar_w - 1)
            page_lines, transmits = self.page_frame(page_w, body_h)
            bar_lines = self.ai_frame(bar_w, body_h)
            body = [p + " " + b for p, b in zip(page_lines, bar_lines)]
            if side == "left":
                # Panels built in page+bar order; swap for left docking.
                body = [b + " " + p for p, b in zip(page_lines, bar_lines)]
        else:
            body, transmits = self.body_lines(outer, body_h)
        frame = "\n".join(head + [""] + body + [""] + runes)
        return frame, transmits

    def page_frame(self, width_outer: int, body_h: int) -> tuple[list[str], list[bytes]]:
        """Page panel at an explicit outer width (for side-by-side layout)."""
        tab = self.tab
        self.pending_transmits = []
        if tab.page is None:
            lines = [art.paint("  (nothing loaded — press o)", P.MUTED)]
            frame = art.panel(lines, title="page", width=width_outer, height=body_h + 2, body_style=(P.SILVER,))
            return frame.splitlines(), []
        width = width_outer - 4
        rows = self.render_rows(tab, width, body_h)
        total = len(rows)
        start = max(0, min(tab.scroll, max(0, total - body_h)))
        tab.scroll = start
        shown = rows[start:start + body_h]
        while len(shown) < body_h:
            shown.append(" " * width)
        title = f"page · {tab.title[:40]}"
        if total > body_h:
            title += f" · {100 * min(total, start + body_h) // max(1, total)}%"
        frame = art.panel(shown, title=title, width=width_outer, height=body_h + 2, body_style=(P.SILVER,))
        return frame.splitlines(), self.pending_transmits

    # ── pixie bar ──
    def model_status(self) -> str:
        return getattr(self, "_model_state", "asleep")

    def ai_frame(self, bar_w: int, body_h: int) -> list[str]:
        tab = self.tab
        width = max(10, bar_w - 4)
        rows: list[str] = []
        import magpie_config as cfg
        if not bool(cfg.effective().get("ai.enabled", True)):
            rows.append(art.paint("pixie is off", P.MUTED))
            rows.append(art.paint("enable her:", P.MUTED))
            rows.append(art.paint("; then ai.enabled", P.MUTED))
        else:
            rows.append(art.paint(f"✦ pixie · {self.model_status()}", P.PINK))
            for role, text in tab.ai_chat[-40:]:
                who = art.paint("you · ", P.MUTED) if role == "you" else art.paint("pixie · ", P.BOLD, P.PINK)
                pieces = art.wrap_plain(text, max(8, width - 8)) or [""]
                rows.append(who + pieces[0])
                for piece in pieces[1:]:
                    rows.append(" " * 8 + piece)
            if tab.ai_typing:
                rows.append(art.paint(f"you · {tab.ai_buf}█", P.SILVER))
            else:
                rows.append(art.paint("a ask · enter send · A hide", P.MUTED))
        # Scroll chat to bottom on new turns; ai_scroll pins older turns.
        total = len(rows)
        start = 0 if total <= body_h else max(0, min(tab.ai_scroll if tab.ai_scroll else total, total - body_h))
        if not tab.ai_scroll and total > body_h:
            start = total - body_h
        shown = rows[start:start + body_h]
        while len(shown) < body_h:
            shown.append(" " * width)
        frame = art.panel(shown, title="pixie", width=bar_w, height=body_h + 2, body_style=(P.SILVER,))
        return frame.splitlines()

    def header_lines(self, outer: int) -> list[str]:
        tab = self.tab
        tabs = " ".join(
            (f"[{k + 1}]" if k == self.cur else f" {k + 1} ") for k in range(len(self.tabs))
        )
        js = "JS:on" if self.js_mode == "on" else ("JS:off" if self.js_mode == "off" else "JS:ask")
        tor = "tor" if self.tor else "clear"
        rows = [f"{tabs}  {js} · {tor}", tab.url or ""]
        if tab.js_badge:
            rows.append(tab.js_badge)
        return art.panel(rows, title=f"magpie · {tab.title[:40]}", width=outer, body_style=(P.MUTED,)).splitlines()

    def runes_lines(self, outer: int) -> list[str]:
        if self.mode == "address":
            line = f"  go ⇄  {self.addr_buf}█"
        elif self.mode == "find":
            line = f"  / {self.find_buf}█"
        elif self.mode == "field":
            line = f"  ✎  {self.edit_buf}█"
        elif self.mode == "ask":
            line = f"  ? {self.ask_prompt}"
        elif self.mode == "settings":
            line = f"  ↑↓ pick · enter edit · esc close"
        elif self.mode == "settings_edit":
            line = f"  ✎  {self.settings_buf}█"
        else:
            msg = self.flash or "o address · Tab hop · a pixie · A bar · ; settings · ? keys · q leave"
            line = f"  {msg}"
        return art.footer_keys([(line, "")], width=outer).splitlines()

    def body_lines(self, outer: int, body_h: int) -> tuple[list[str], list[bytes]]:
        tab = self.tab
        self.pending_transmits = []
        if self.mode == "overlay" and self.overlay_rows:
            return self.overlay_frame(outer, body_h), []
        if self.mode == "settings" or self.mode == "settings_edit":
            return self.settings_frame(outer, body_h), []
        return self.page_frame(outer, body_h)

    def overlay_frame(self, outer: int, body_h: int) -> list[str]:
        width = outer - 4
        wrapped: list[str] = []
        for raw in self.overlay_rows:
            plain = art.strip_ansi(raw)
            if art.vis_len(plain) <= width:
                wrapped.append(raw if raw else " ")
            else:
                wrapped.extend(art.wrap_plain(plain, width) or [" "])
        total = len(wrapped)
        if self.overlay_actions and self.overlay_actions[0][0] == "close":
            start = max(0, min(self.overlay_sel, max(0, total - body_h)))
        else:
            start = 0
        shown = wrapped[start:start + body_h]
        while len(shown) < body_h:
            shown.append(" " * width)
        title = self.overlay_title or "overlay"
        if total > body_h:
            title += f" · {100 * min(total, start + body_h) // max(1, total)}%"
        frame = art.panel(shown, title=title, width=outer, height=body_h + 2, body_style=(P.SILVER,))
        return frame.splitlines()

    def render_rows(self, tab: Tab, width: int, body_h: int) -> list[str]:
        assert tab.page is not None
        out: list[str] = []
        focus = self.focused_target()
        for i, line in enumerate(tab.page.lines):
            segs = line.segments
            # Image lines become pixel placements in kitty, thumbnails otherwise.
            if line.medias and self.is_image_media(tab, line.medias[0]):
                out.extend(self.image_rows(tab, line.medias[0], width))
                continue
            if line.medias and self.is_video_media(tab, line.medias[0]):
                out.extend(self.poster_rows(tab, line.medias[0], width))
                continue
            text = self.styled_line(segs, width)
            if focus is not None:
                kind, ident = focus
                if (kind == "link" and ident in line.links) or (kind == "media" and ident in line.medias) or (kind == "field" and ident in line.fields):
                    inner = art.strip_ansi(text)
                    # Clip to make room for the focus marker, then mark + bold.
                    cut, w = [], 0
                    for ch in inner:
                        cw = art.vis_len(ch)
                        if w + cw > width - 2:
                            break
                        cut.append(ch)
                        w += cw
                    text = art.paint("► ", P.BOLD, P.PINK) + art.paint("".join(cut), P.BOLD, P.SILVER)
                    text += " " * max(0, width - 2 - w)
            if tab.find and tab.find.lower() in art.strip_ansi(text).lower():
                text = self.highlight(text, tab.find)
            # Pad/truncate to width.
            vis = art.vis_len(art.strip_ansi(text))
            if vis < width:
                text += " " * (width - vis)
            out.append(text)
        return out

    def styled_line(self, segs: list[Segment], width: int) -> str:
        parts: list[str] = []
        used = 0
        for seg in segs:
            if used >= width:
                break
            chunk = seg.text
            # Clip to width by visible cells.
            room = width - used
            if art.vis_len(chunk) > room:
                cut = []
                w = 0
                for ch in chunk:
                    cw = art.vis_len(ch)
                    if w + cw > room:
                        break
                    cut.append(ch)
                    w += cw
                chunk = "".join(cut)
            used += art.vis_len(chunk)
            codes = []
            if seg.fg is not None:
                codes.append(_ansi_for(seg.fg, False, self.truecolor))
            if seg.bg is not None:
                codes.append(_ansi_for(seg.bg, True, self.truecolor))
            if seg.bold:
                codes.append(P.BOLD)
            if seg.italic:
                codes.append(P.ITALIC)
            if seg.underline:
                codes.append("\033[4m")
            if seg.strike:
                codes.append("\033[9m")
            if seg.link and seg.fg is None:
                codes.append(P.PINK)
                codes.append(P.BOLD)
            parts.append(art.paint(chunk, *codes) if codes else chunk)
        return "".join(parts)

    def highlight(self, text: str, query: str) -> str:
        plain = art.strip_ansi(text)
        out = []
        low = plain.lower()
        q = query.lower()
        i = 0
        for m in re.finditer(re.escape(q), low):
            out.append(plain[i:m.start()])
            out.append(art.paint(plain[m.start():m.end()], P.BOLD, P.PINK, "\033[48;5;53m"))
            i = m.end()
        out.append(plain[i:])
        return "".join(out)

    # ── images ──
    def is_image_media(self, tab: Tab, ident: int) -> bool:
        if tab.page is None or ident < 1 or ident > len(tab.page.media):
            return False
        m = tab.page.media[ident - 1]
        return m.kind == "image" and bool(m.url)

    def inline_allowed(self, tab: Tab, ident: int) -> bool:
        import magpie_config as cfg
        try:
            cap = max(1, min(64, int(cfg.effective().get("media.inline_images", 8))))
        except (TypeError, ValueError):
            cap = 8
        if tab.page is None:
            return False
        position = 0
        for m in tab.page.media:
            if m.kind not in ("image", "video"):
                continue
            position += 1
            if m.ident == ident:
                return position <= cap
        return False

    def image_rows(self, tab: Tab, ident: int, width: int) -> list[str]:
        m = tab.page.media[ident - 1]
        key = (ident, width)
        cached = tab.img_cache.get(key, _MISSING)
        if cached is _MISSING:
            if self.inline_allowed(tab, ident):
                if key not in tab.img_pending:
                    tab.img_pending.add(key)
                    self.loader.request({"kind": "image", "url": m.url, "width": width, "key": key, "tab": tab})
                label = art.paint(f"  [image {ident}: {m.alt[:50]} — fetching…]", P.MUTED)
            else:
                label = art.paint(f"  [image {ident}: {m.alt[:50]} — i loads]", P.MUTED)
            return [label]
        if cached is None or cached.get("kind") == "failed":
            return [art.paint(f"  [image {ident}: {m.alt[:60] or m.url[:60]} — would not load]", P.WARN)]
        kind = cached["kind"]
        if kind == "kitty":
            img: DisplayImage = cached["img"]
            if img.image_id not in tab.img_ids:
                tab.img_ids.append(img.image_id)
                cached["transmit"] = True
            if cached.get("transmit"):
                cached["transmit"] = False
                self.pending_transmits.append(kitty_transmit(img))
            return kitty_placeholder_lines(img.image_id, img.cols, img.rows)
        rows: list[str] = cached["rows"]
        label = art.paint(f"  [image {ident}: {m.alt[:50]}]", P.PINK)
        return [label] + rows

    def load_image_data(self, url: str, width: int) -> dict | None:
        """Fetch + prepare one image. Thread-safe: may run on the loader."""
        import magpie_config as cfg
        cap_mb = int(cfg.effective().get("media.image_cap_mb", 12))
        max_cols = max(16, min(width - 4, 72))
        max_rows = 10
        try:
            if url.startswith("file://"):
                data = Path(urllib.parse.urlparse(url).path).read_bytes()
                ctype = ""
            elif url.startswith("data:"):
                resp = parse_data_url(url)
                data = resp.data
                ctype = resp.content_type
            else:
                resp = self.client.request(url, top_level=False)
                if resp.status >= 400:
                    return None
                data = resp.data
                ctype = resp.content_type
        except (FetchError, OSError, ValueError):
            return None
        if len(data) > max(1, cap_mb) * 1024 * 1024:
            return None
        if self.kitty:
            try:
                with self._id_lock:
                    image_id = self.next_image_id
                    self.next_image_id += 1
                    if self.next_image_id > 0xFFFFFF:
                        self.next_image_id = 1
                img = prepare_display_image(image_id, data, ctype, max_cols, max_rows)
            except FetchError:
                return self.ansi_image(data, ctype, max_cols, max_rows)
            return {"kind": "kitty", "img": img}
        return self.ansi_image(data, ctype, max_cols, max_rows)

    def ansi_image(self, data: bytes, ctype: str, max_cols: int, max_rows: int) -> dict | None:
        from magpie_image import detect_format as _df
        fmt = _df(data, ctype)
        try:
            if fmt == "png":
                w, h, rgb = decode_png(data)
            elif fmt == "gif":
                w, h, rgb = decode_gif(data)
            elif fmt == "bmp":
                w, h, rgb = decode_bmp(data)
            else:
                w, h, rgb = rasterize_with_ffmpeg(data, ".img", max_side=320)
        except FetchError:
            return None
        cols, rows = fit_cells(w, h, max_cols, max_rows)
        return {"kind": "ansi", "rows": ansi_thumbnail(rgb, w, h, cols, rows)}

    def is_video_media(self, tab: Tab, ident: int) -> bool:
        if tab.page is None or ident < 1 or ident > len(tab.page.media):
            return False
        m = tab.page.media[ident - 1]
        return m.kind == "video" and bool(m.url)

    def poster_rows(self, tab: Tab, ident: int, width: int) -> list[str]:
        m = tab.page.media[ident - 1]
        key = (f"poster-{ident}", width)
        cached = tab.img_cache.get(key, _MISSING)
        label = art.paint(f"  [video {ident}: {m.title[:50] or m.url[:60]} — v plays]", P.PINK)
        if cached is _MISSING:
            if self.inline_allowed(tab, ident):
                if key not in tab.img_pending:
                    tab.img_pending.add(key)
                    self.loader.request({"kind": "poster", "url": m.url, "width": width, "key": key, "tab": tab})
                return [label, art.paint("  (poster fetching…)", P.MUTED)]
            return [label]
        if cached is None or cached.get("kind") == "failed":
            return [label]
        if cached["kind"] == "kitty":
            img: DisplayImage = cached["img"]
            if img.image_id not in tab.img_ids:
                tab.img_ids.append(img.image_id)
                cached["transmit"] = True
            if cached.get("transmit"):
                cached["transmit"] = False
                self.pending_transmits.append(kitty_transmit(img))
            return [label] + kitty_placeholder_lines(img.image_id, img.cols, img.rows)
        return [label] + cached["rows"]

    def load_poster_data(self, url: str, width: int) -> dict | None:
        """Fetch + thumbnail one video. Thread-safe: may run on the loader."""
        import magpie_config as cfg
        cap_mb = int(cfg.effective().get("media.video_cap_mb", 12))
        max_cols = max(16, min(width - 4, 72))
        max_rows = 8
        try:
            if url.startswith("file://"):
                path = Path(urllib.parse.urlparse(url).path)
                if not path.is_file() or path.stat().st_size > 48_000_000:
                    return None
            elif url.startswith("data:"):
                resp = parse_data_url(url)
                path = cache_media_bytes(resp.data, ".vid")
            else:
                resp = self.client.request(url, top_level=False, max_bytes=max(1, cap_mb) * 1024 * 1024)
                if resp.status >= 400 or not resp.data:
                    return None
                path = cache_media_bytes(resp.data, _suffix_for(resp) or ".vid")
        except (FetchError, OSError, ValueError):
            return None
        try:
            w, h, rgb = video_thumbnail(path, max_side=320)
        except FetchError:
            return None
        cols, rows = fit_cells(w, h, max_cols, max_rows)
        if self.kitty:
            with self._id_lock:
                image_id = self.next_image_id
                self.next_image_id += 1
                if self.next_image_id > 0xFFFFFF:
                    self.next_image_id = 1
            img = DisplayImage(image_id, "rgb", w, h, rgb, cols, rows)
            return {"kind": "kitty", "img": img}
        return {"kind": "ansi", "rows": ansi_thumbnail(rgb, w, h, cols, rows)}

    # ── main loop ──
    def run(self, start_url: str = "", *, no_wizard: bool = False) -> int:
        import magpie_config as cfg
        try:
            import faulthandler
            log = Path.home() / ".cache" / "magpie" / "crash.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            faulthandler.enable(file=open(log, "w", encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if not no_wizard:
            cfg.offer_first_run()
        if not start_url:
            start_url = str(cfg.effective().get("browse.homepage", "magpie:start")) or "magpie:start"
        fd = art.tui_open_tty()
        if fd is None:
            print("magpie browse: needs a real terminal (try: magpie browse --dump URL)", file=sys.stderr)
            return 2
        self.fd = fd
        self.reader = InputReader(fd)
        self.pending_transmits = []
        art.tui_begin(fd, "magpie")
        try:
            min_w, min_h = 44, 14
            if art.term_width() < min_w or art.term_height() < min_h:
                art.tty_write(fd, art.clear_screen() + "magpie: terminal too small (need 44x14).\n")
                try:
                    self.reader.read(timeout=3)
                except OSError:
                    pass
                return 1
            self.navigate(start_url or "magpie:start", push=True)
            while True:
                self.pending_transmits = []
                try:
                    self.paint()
                except OSError:
                    pass
                # Flush any fresh kitty payloads (collected during render).
                try:
                    ev = self.reader.read(timeout=0.2)
                except OSError:
                    ev = ""
                if ev == "":
                    self.tick()
                    continue
                if isinstance(ev, art.MouseEvent):
                    try:
                        self.on_mouse(ev)
                    except (OSError, ValueError):
                        pass
                    continue
                try:
                    self.on_key(ev)
                except SystemExit:
                    raise
                except KeyboardInterrupt:
                    raise
                except Exception as e:  # never let one bad keystroke kill the den
                    self.flash = f"magpie tripped ({e}) — carry on"
        except SystemExit as e:
            return int(e.code or 0)
        except KeyboardInterrupt:
            return 130
        except Exception as e:
            # Last resort: restore the terminal, then speak like a fae, not a traceback.
            try:
                art.tui_cleanup()
            except (OSError, ValueError):
                pass
            print(f"magpie: the den collapsed ({e})", file=sys.stderr)
            print("  next:  try again; if it repeats, run with FAE_DEBUG=1 and tell a human", file=sys.stderr)
            return 1
        finally:
            try:
                self.player.stop()
            except (OSError, ValueError):
                pass
            art.tui_cleanup()

    def tick(self) -> None:
        # Periodic: reap finished media, keep status fresh.
        if self.player.running():
            self.flash = self.player.status()
        try:
            while True:
                task, result = self.loader.done.get_nowait()
                tab = task.get("tab")
                key = task.get("key")
                if tab is not None and key is not None:
                    tab.img_pending.discard(key)
                    if key not in tab.img_cache:
                        tab.img_cache[key] = result
        except queue.Empty:
            pass
        try:
            while True:
                gen, tab, turn = self.ai_done.get_nowait()
                if gen == self.ai_gen:
                    tab.ai_chat.append(turn)
                    tab.ai_scroll = 0
                    self.ai_busy = False
        except queue.Empty:
            pass
        now = time.monotonic()
        if now - self._model_checked > 30:
            self._model_checked = now
            try:
                self._model_state = "ready · local" if legacy_magpie().llm_up() else "asleep"
            except (ImportError, OSError, ValueError):
                self._model_state = "unknown"

    def on_mouse(self, ev: art.MouseEvent) -> None:
        tab = self.tab
        delta = art.wheel_delta(ev)
        if delta and tab.page is not None:
            tab.scroll = max(0, tab.scroll + (-3 if delta > 0 else 3))
            return
        if ev.action == "press" and ev.button == 0 and tab.page is not None:
            # Map y to a content row (header offset is approximate: header + blank).
            tw = art.term_width()
            outer = max(36, min(tw, 110))
            page_x0 = 0
            if tab.ai_open:
                import magpie_config as cfg
                bar_w = min(46, max(28, outer * 38 // 100))
                if str(cfg.effective().get("browse.ai_bar", "right")) == "left":
                    page_x0 = bar_w + 1
            if ev.x - 1 < page_x0:
                return  # clicked the pixie bar (keyboard lives there)
            head_h = len(self.header_lines(outer))
            row = tab.scroll + (ev.y - head_h - 1)
            if 0 <= row < len(tab.page.lines):
                line = tab.page.lines[row]
                target = None
                if line.links:
                    target = ("link", line.links[0])
                elif line.medias:
                    target = ("media", line.medias[0])
                elif line.fields:
                    target = ("field", line.fields[0])
                if target is not None:
                    items = self.focusables()
                    if target in items:
                        tab.focus = items.index(target)
                        self.activate()

    def on_key(self, key: str) -> None:
        if self.mode == "address":
            self.address_key(key)
            return
        if self.mode == "find":
            self.find_key(key)
            return
        if self.mode == "field":
            self.field_key(key)
            return
        if self.mode == "overlay":
            self.overlay_key(key)
            return
        if self.mode == "settings":
            self.settings_key(key)
            return
        if self.mode == "settings_edit":
            self.settings_edit_key(key)
            return
        tab = self.tab
        if tab.ai_typing:
            self.ai_key(key)
            return
        if key in ("q", "ctrl-c"):
            self.close_tab()
        elif key == "ctrl-d":
            raise SystemExit(0)
        elif key in ("j", "down"):
            self.move_focus(1)
        elif key in ("k", "up"):
            self.move_focus(-1)
        elif key == "tab":
            self.move_focus(1)
        elif key == "shift-tab":
            self.move_focus(-1)
        elif key == "right":
            self.move_focus(1)
        elif key == "left":
            self.move_focus(-1)
        elif key in ("pgdn", "space"):
            tab.scroll += self.page_h()
        elif key == "pgup":
            tab.scroll = max(0, tab.scroll - self.page_h())
        elif key == "home" or key == "g":
            tab.scroll = 0
            tab.focus = 0
        elif key == "end" or key == "G":
            tab.scroll = 10**9
            items = self.focusables()
            tab.focus = max(0, len(items) - 1)
        elif key == "enter":
            self.activate()
        elif key == "o":
            self.mode = "address"
            self.addr_buf = "" if tab.url.startswith("magpie:") else tab.url
        elif key == "/":
            self.mode = "find"
            self.find_buf = tab.find
        elif key == "n":
            self.find_next(1)
        elif key == "N":
            self.find_next(-1)
        elif key == "b":
            self.go_back()
        elif key == "F":
            self.go_forward()
        elif key == "r":
            self.reload()
        elif key == "H":
            self.navigate("magpie:history")
        elif key == "B":
            self.navigate("magpie:bookmarks")
        elif key == "M":
            self.navigate("magpie:media")
        elif key == "m":
            self.bookmark_page()
        elif key == "L":
            self.import_lynx()
        elif key == "C":
            clear_history()
            self.flash = "history cleared"
        elif key == "J":
            self.cycle_js()
        elif key == "R":
            self.toggle_reader()
        elif key == "a":
            if tab.ai_open and not tab.ai_typing:
                tab.ai_typing = True
            else:
                self.ai_summarize()
        elif key == "A":
            tab.ai_open = not tab.ai_open
            tab.ai_typing = False
        elif key == ";":
            self.open_settings()
        elif key == "e":
            self.open_external()
        elif key == "y":
            self.yank_url()
        elif key == "v":
            self.play_focused()
        elif key == "i":
            self.fullscreen_image()
        elif key == "d":
            self.download_focused()
        elif key == "D":
            self.navigate("magpie:downloads")
        elif key == "s":
            self.save_page()
        elif key == "?":
            self.navigate("magpie:help")
        elif key == "t":
            self.new_tab()
        elif key == "W":
            self.close_tab()
        elif key == "{":
            self.cur = (self.cur - 1) % len(self.tabs)
        elif key == "}":
            self.cur = (self.cur + 1) % len(self.tabs)
        elif key == "ctrl-t":
            self.new_tab()
        elif key == "ctrl-w":
            self.close_tab()
        elif key in ("x", "X"):
            if self.player.running():
                self.player.stop()
                self.flash = "mpv stopped"
        elif key == "esc":
            self.loader.cancel()
            for t in self.tabs:
                t.img_pending.clear()
            if self.ai_busy:
                self.ai_abandon()
                self.flash = "pixie stood down"
            tab.find = ""
            tab.find_rows = []

    def page_h(self) -> int:
        th = art.term_height()
        head_h = len(self.header_lines(max(36, min(art.term_width(), 110))))
        return max(3, th - head_h - 4)

    def move_focus(self, step: int) -> None:
        tab = self.tab
        items = self.focusables()
        if not items:
            tab.scroll = max(0, tab.scroll + step)
            return
        tab.focus = (tab.focus + step) % len(items)
        self.ensure_focus_visible(self.page_h())

    def activate(self) -> None:
        tab = self.tab
        target = self.focused_target()
        if target is None or tab.page is None:
            return
        kind, ident = target
        if kind == "link":
            link = tab.page.links[ident - 1]
            self.navigate(link.url)
        elif kind == "media":
            m = tab.page.media[ident - 1]
            if m.kind in ("video", "audio"):
                self.play_url(m.url)
            elif m.kind == "frame":
                self.navigate(m.url)
            elif m.kind == "object":
                self.navigate(m.url)
            else:
                self.fullscreen_image()
        elif kind == "field":
            self.edit_field(ident)

    def go_back(self) -> None:
        tab = self.tab
        if tab.hindex > 0:
            tab.hindex -= 1
            self.clear_images(tab)
            self.navigate(tab.history[tab.hindex], push=False)

    def go_forward(self) -> None:
        tab = self.tab
        if tab.hindex < len(tab.history) - 1:
            tab.hindex += 1
            self.clear_images(tab)
            self.navigate(tab.history[tab.hindex], push=False)

    def reload(self) -> None:
        tab = self.tab
        if tab.history and tab.hindex >= 0:
            self.clear_images(tab)
            self.navigate(tab.history[tab.hindex], push=False)

    def find_next(self, step: int) -> None:
        tab = self.tab
        if tab.page is None or not tab.find:
            return
        if not tab.find_rows or tab.find_rows != find_text_rows(tab.page, tab.find):
            tab.find_rows = find_text_rows(tab.page, tab.find)
        if not tab.find_rows:
            self.flash = f"no '{tab.find}' on this page"
            return
        tab.find_idx = (tab.find_idx + step) % len(tab.find_rows)
        tab.scroll = max(0, tab.find_rows[tab.find_idx] - 2)

    # ── address / find / field editing ──
    def address_key(self, key: str) -> None:
        if key == "enter":
            self.mode = "browse"
            self.navigate(self.addr_buf)
        elif key == "esc":
            self.mode = "browse"
        elif key == "backspace":
            self.addr_buf = self.addr_buf[:-1]
        elif key == "ctrl-u":
            self.addr_buf = ""
        elif key == "ctrl-w":
            self.addr_buf = re.sub(r"\S+\s*$", "", self.addr_buf)
        elif isinstance(key, str) and len(key) == 1 and key.isprintable():
            self.addr_buf += key

    def find_key(self, key: str) -> None:
        tab = self.tab
        if key == "enter" or key == "esc":
            self.mode = "browse"
            tab.find = self.find_buf
            tab.find_rows = find_text_rows(tab.page, tab.find) if tab.page and tab.find else []
            tab.find_idx = -1
            if tab.find_rows:
                self.find_next(1)
            elif tab.find:
                self.flash = f"no '{tab.find}' on this page"
        elif key == "backspace":
            self.find_buf = self.find_buf[:-1]
        elif key == "ctrl-u":
            self.find_buf = ""
        elif isinstance(key, str) and len(key) == 1 and key.isprintable():
            self.find_buf += key

    def edit_field(self, ident: int) -> None:
        tab = self.tab
        assert tab.page is not None
        fld = tab.page.fields[ident - 1]
        if fld.kind in ("checkbox", "radio"):
            tab.form_state[ident] = not tab.form_state.get(ident, fld.checked)
            if fld.kind == "radio" and tab.form_state[ident]:
                for other in tab.page.fields:
                    if other.kind == "radio" and other.name == fld.name and other.ident != ident:
                        tab.form_state[other.ident] = False
            self.refresh_field_rows(tab)
            return
        if fld.kind in ("submit", "button", "image"):
            form = next((f for f in tab.page.forms if f.ident == fld.form), None)
            if form is not None:
                self.submit_form(tab, form)
            else:
                self.fail("button without a form")
            return
        if fld.kind == "select":
            self.select_overlay(ident)
            return
        if fld.kind == "file":
            self.fail("file uploads are not supported")
            return
        self.mode = "field"
        self.field_edit = (ident, fld.kind)
        self.edit_buf = str(tab.form_state.get(ident, fld.value))

    def field_key(self, key: str) -> None:
        tab = self.tab
        assert self.field_edit is not None
        ident, kind = self.field_edit
        if key == "enter":
            tab.form_state[ident] = self.edit_buf
            self.mode = "browse"
            self.field_edit = None
            self.refresh_field_rows(tab)
            # Submit on enter for single-line inputs inside a form?
            fld = tab.page.fields[ident - 1] if tab.page else None
            if fld is not None and kind in ("text", "password", "search", "url", "email"):
                form = next((f for f in tab.page.forms if f.ident == fld.form), None)
                if form is not None and len(form.fields) == 1:
                    self.submit_form(tab, form)
        elif key == "esc":
            self.mode = "browse"
            self.field_edit = None
        elif key == "backspace":
            self.edit_buf = self.edit_buf[:-1]
        elif key == "ctrl-u":
            self.edit_buf = ""
        elif isinstance(key, str) and len(key) == 1 and (key.isprintable() or key == " "):
            self.edit_buf += key

    def refresh_field_rows(self, tab: Tab) -> None:
        if tab.page is None:
            return
        # Re-render field labels from form_state without refetching.
        for fld in tab.page.fields:
            if fld.ident in tab.form_state:
                val = tab.form_state[fld.ident]
                if isinstance(val, str):
                    fld.value = val
                elif isinstance(val, bool):
                    fld.checked = val
        width = tab.layout_w
        tab.page = layout_dom(tab.page.root, tab.page.url, width, js_enabled=False, title_override=tab.page.title)

    def select_overlay(self, ident: int) -> None:
        tab = self.tab
        assert tab.page is not None
        fld = tab.page.fields[ident - 1]
        self.mode = "overlay"
        self.overlay_title = f"choose · {fld.name or 'option'}"
        self.overlay_rows = [t for t, _, _ in fld.options] or ["(no options)"]
        self.overlay_sel = next((k for k, (_, _, s) in enumerate(fld.options) if s), 0)
        self.overlay_actions = [("pick", ident)]

    # ── settings overlay (same file the CLI wizard writes) ──
    def settings_rows(self) -> list[tuple[str, str, str]]:
        import magpie_config as cfg
        current = cfg.effective()
        rows = []
        for section, keys in cfg.SECTIONS:
            rows.append((f"[{section}]", "", ""))
            for key in keys:
                rows.append((key, str(current[key]), cfg.HELP.get(key, "")))
        return rows

    def open_settings(self) -> None:
        self.mode = "settings"
        self.settings_sel = 0
        self.settings_buf = ""

    def settings_frame(self, outer: int, body_h: int) -> list[str]:
        width = outer - 4
        rows = self.settings_rows()
        shown: list[str] = []
        for i, (key, value, hint) in enumerate(rows):
            if key.startswith("["):
                shown.append(art.paint(f"  {key}", P.BOLD, P.PINK))
                continue
            mark = art.paint("► ", P.BOLD, P.PINK) if i == self.settings_sel else "  "
            line = f"{mark}{key} = {value}"
            if hint:
                line += art.paint(f"  ·  {hint}", P.MUTED)
            shown.append(art.truncate_vis(art.strip_ansi(line), width) if art.vis_len(art.strip_ansi(line)) > width else line)
        while len(shown) < body_h:
            shown.append(" " * width)
        frame = art.panel(shown[:body_h] if len(shown) > body_h else shown, title="settings · magpie config", width=outer, height=body_h + 2, body_style=(P.SILVER,))
        return frame.splitlines()

    def settings_key(self, key: str) -> None:
        rows = self.settings_rows()
        if key in ("esc", "q"):
            self.mode = "browse"
            return
        if key in ("up", "k"):
            self.settings_sel = max(0, self.settings_sel - 1)
            while self.settings_rows()[self.settings_sel][0].startswith("[") and self.settings_sel > 0:
                self.settings_sel -= 1
        elif key in ("down", "j"):
            self.settings_sel = min(len(rows) - 1, self.settings_sel + 1)
            while self.settings_rows()[self.settings_sel][0].startswith("[") and self.settings_sel < len(rows) - 1:
                self.settings_sel += 1
        elif key == "enter":
            name = rows[self.settings_sel][0]
            if not name.startswith("["):
                import magpie_config as cfg
                self.mode = "settings_edit"
                self.settings_edit_key_name = name
                self.settings_buf = str(cfg.effective()[name])

    def settings_edit_key(self, key: str) -> None:
        if key == "enter":
            import magpie_config as cfg
            name = getattr(self, "settings_edit_key_name", "")
            try:
                cfg.set_key(name, self.settings_buf)
                self.flash = f"{name} = {cfg.get(name)}"
                self.apply_settings(name)
            except cfg.ConfigError as e:
                self.fail(str(e))
                return
            self.mode = "settings"
        elif key == "esc":
            self.mode = "settings"
        elif key == "backspace":
            self.settings_buf = self.settings_buf[:-1]
        elif key == "ctrl-u":
            self.settings_buf = ""
        elif isinstance(key, str) and len(key) == 1 and (key.isprintable() or key == " "):
            self.settings_buf += key

    def apply_settings(self, name: str) -> None:
        import magpie_config as cfg
        value = cfg.effective()[name]
        if name == "browse.js" and not self.js_locked:
            self.js_mode = str(value)
            self.flash += " (reload to apply)"
        elif name == "search.tor" and not self.tor_locked:
            self.tor = bool(value)
            self.client = HttpClient(tor=self.tor, timeout=25.0)
            self.flash += " (fresh cookie jar)"
        elif name == "ai.enabled":
            pass
        elif name == "browse.ai_bar":
            pass

    def overlay_key(self, key: str) -> None:
        action = self.overlay_actions[0][0] if self.overlay_actions else "close"
        if key in ("esc", "q"):
            self.mode = "browse"
            return
        if key in ("up", "k"):
            self.overlay_sel = max(0, self.overlay_sel - 1)
        elif key in ("down", "j", "pgdn", "space"):
            self.overlay_sel += 1
        elif key == "pgup":
            self.overlay_sel = max(0, self.overlay_sel - 10)
        elif key == "enter":
            if action == "pick":
                tab = self.tab
                _, ident = self.overlay_actions[0]
                assert tab.page is not None
                fld = tab.page.fields[ident - 1]
                if fld.options and 0 <= self.overlay_sel < len(fld.options):
                    _, value, _ = fld.options[self.overlay_sel]
                    tab.form_state[ident] = value
                    fld.value = value
                    self.refresh_field_rows(tab)
            self.mode = "browse"
            return
        else:
            return
        if action == "pick":
            self.overlay_sel = max(0, min(len(self.overlay_rows) - 1, self.overlay_sel))

    # ── misc actions ──
    def bookmark_page(self) -> None:
        tab = self.tab
        marks = load_bookmarks()
        if any(m["url"] == tab.url for m in marks):
            self.flash = "already bookmarked"
            return
        marks.append({"title": tab.title, "url": tab.url})
        try:
            save_bookmarks(marks)
            self.flash = f"bookmarked {tab.title[:40]}"
        except OSError as e:
            self.fail(f"could not save bookmark ({e})")

    def import_lynx(self) -> None:
        try:
            rows = import_lynx_bookmarks()
        except FetchError as e:
            self.fail(str(e))
            return
        marks = load_bookmarks()
        seen = {m["url"] for m in marks}
        for r in rows:
            if r["url"] not in seen:
                marks.append(r)
                seen.add(r["url"])
        try:
            save_bookmarks(marks)
            self.flash = f"imported {len(rows)} lynx bookmark(s)"
        except OSError as e:
            self.fail(f"could not save bookmarks ({e})")

    def cycle_js(self) -> None:
        order = ["ask", "on", "off"]
        self.js_mode = order[(order.index(self.js_mode) + 1) % 3]
        self.js_allow.clear()
        self.js_deny.clear()
        self.flash = f"scripts: {self.js_mode} (reload to apply)"
        if self.js_mode != "ask":
            self.reload()

    def toggle_reader(self) -> None:
        tab = self.tab
        if tab.page is None:
            return
        if not tab.reader:
            article = extract_article(tab.page)
            html = f"<html><head><title>{_escape(tab.title)}</title></head><body><h1>{_escape(tab.title)}</h1><p>{_escape(article)}</p></body></html>"
            width = tab.layout_w
            tab.page = build_page(tab.url, html, width)
            tab.reader = True
            tab.scroll = 0
            self.flash = "reader view (R to leave)"
        else:
            tab.reader = False
            self.reload()

    def ai_summarize(self) -> None:
        """Summarize the current page into the pixie bar (never blocks the UI)."""
        import magpie_config as cfg
        tab = self.tab
        if tab.page is None:
            return
        if not bool(cfg.effective().get("ai.enabled", True)):
            self.fail("pixie is off — enable her with ; then ai.enabled")
            return
        try:
            legacy = legacy_magpie()
        except (ImportError, OSError) as e:
            self.fail(f"pixie half missing ({e})")
            return
        tab.ai_open = True
        if self.ai_busy:
            self.flash = "pixie is already thinking (esc abandons her)"
            return
        if not legacy.llm_up():
            self._model_state, self._model_checked = "asleep", time.monotonic()
            self.fail("no local model awake (try: menagerie ensure magpie)")
            return
        article = extract_article(tab.page)
        ctx = f"Page: {tab.url}\n\n{article[:5000]}"
        self._ai_start(tab, "pixie is reading the page…", tab.title, ctx)

    def ai_send(self) -> None:
        """Send the bar's follow-up question about the current page."""
        import magpie_config as cfg
        tab = self.tab
        question = tab.ai_buf.strip()
        tab.ai_buf = ""
        tab.ai_typing = False
        if not question or tab.page is None:
            return
        if not bool(cfg.effective().get("ai.enabled", True)):
            self.fail("pixie is off — enable her with ; then ai.enabled")
            return
        try:
            legacy = legacy_magpie()
        except (ImportError, OSError) as e:
            self.fail(f"pixie half missing ({e})")
            return
        if self.ai_busy:
            self.flash = "pixie is already thinking (esc abandons her)"
            return
        if not legacy.llm_up():
            self.fail("no local model awake (try: menagerie ensure magpie)")
            return
        tab.ai_chat.append(("you", question))
        tab.ai_scroll = 0
        article = extract_article(tab.page)
        history = "\n".join(f"{role}: {text[:800]}" for role, text in tab.ai_chat[-7:-1])
        ctx = f"Page: {tab.url}\n\n{article[:4000]}\n\nConversation so far:\n{history}\n\nFollow-up question: {question}"
        self._ai_start(tab, "pixie is thinking…", question, ctx)

    def _ai_start(self, tab: Tab, status: str, prompt: str, ctx: str) -> None:
        self.ai_busy = True
        gen = self.ai_gen
        self.status(status)
        if hasattr(self, "fd"):
            self.paint()

        def job() -> None:
            try:
                answer = legacy_magpie().ai_summary(prompt, ctx)
            except (RuntimeError, OSError, ValueError) as e:
                answer = f"(pixie stumbled: {e})"
            except Exception as e:
                answer = f"(pixie tripped: {e})"
            try:
                self.ai_done.put((gen, tab, ("pixie", answer or "(pixie said nothing)")))
            except queue.Full:
                pass

        threading.Thread(target=job, daemon=True).start()

    def ai_abandon(self) -> None:
        """Drop a running AI job's result (the thread itself can't be killed)."""
        self.ai_gen += 1
        self.ai_busy = False

    def ai_key(self, key: str) -> None:
        tab = self.tab
        if key == "enter":
            self.ai_send()
        elif key == "esc":
            tab.ai_typing = False
            tab.ai_buf = ""
        elif key == "backspace":
            tab.ai_buf = tab.ai_buf[:-1]
        elif key == "ctrl-u":
            tab.ai_buf = ""
        elif key == "pgup":
            tab.ai_scroll = max(0, (tab.ai_scroll or 10**9) - 5)
        elif key == "pgdn":
            tab.ai_scroll += 5
        elif isinstance(key, str) and len(key) == 1 and (key.isprintable() or key == " "):
            tab.ai_buf += key

    def open_external(self) -> None:
        tab = self.tab
        if not tab.url.startswith("http"):
            self.fail("nothing external to open here")
            return
        if not shutil.which("zen-browser"):
            self.fail("zen-browser is not installed")
            return
        try:
            art.tui_suspend()
            subprocess.Popen(["zen-browser", tab.url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            self.flash = "opened in zen"
        except OSError as e:
            self.fail(f"zen would not start ({e})")
        finally:
            art.tui_resume()

    def yank_url(self) -> None:
        tab = self.tab
        if not tab.url:
            return
        # OSC52 clipboard (kitty honors it).
        payload = tab.url.encode("utf-8")
        import base64 as _b64
        seq = b"\x1b]52;c;" + _b64.b64encode(payload) + b"\x07"
        try:
            os.write(self.fd, seq)
            self.flash = "address yanked"
        except OSError:
            self.fail("clipboard unreachable")

    def play_focused(self) -> None:
        tab = self.tab
        if tab.page is None:
            return
        target = self.focused_target()
        if target is None:
            self.fail("no media under the cursor")
            return
        kind, ident = target
        if kind == "media":
            m = tab.page.media[ident - 1]
            if m.kind in ("video", "audio"):
                self.play_url(m.url)
            elif m.kind == "image":
                self.fullscreen_image()
            else:
                self.navigate(m.url)
        elif kind == "link":
            self.play_url(tab.page.links[ident - 1].url)

    def fullscreen_image(self) -> None:
        tab = self.tab
        if tab.page is None:
            return
        target = self.focused_target()
        ident = None
        if target is not None and target[0] == "media" and tab.page.media[target[1] - 1].kind == "image":
            ident = target[1]
        else:
            for m in tab.page.media:
                if m.kind == "image":
                    ident = m.ident
                    break
        if ident is None:
            self.fail("no image on this page")
            return
        m = tab.page.media[ident - 1]
        key = (ident, 400)
        cached = tab.img_cache.get(key, _MISSING)
        if cached is _MISSING:
            if key not in tab.img_pending:
                tab.img_pending.add(key)
                self.loader.request({"kind": "image", "url": m.url, "width": 400, "key": key, "tab": tab})
            self.flash = "fetching image… (i again to view)"
            return
        if cached is None or cached.get("kind") != "kitty":
            self.fail("fullscreen needs kitty pixels")
            return
        img: DisplayImage = cached["img"]
        cols, rows = art.term_width() - 2, art.term_height() - 3
        try:
            art.tui_suspend()
            fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
            try:
                os.write(fd, b"\x1b[H\x1b[2J\x1b[?25l")
                os.write(fd, kitty_transmit(DisplayImage(img.image_id, img.mode, img.width, img.height, img.payload, cols, rows)))
                for line in kitty_placeholder_lines(img.image_id, cols, rows):
                    os.write(fd, (line + "\n").encode("utf-8"))
                hint = f"\x1b[{art.term_height()};1H\x1b[0m  Enter to return\x1b[K"
                os.write(fd, hint.encode())
                self.reader.read(timeout=60)
                os.write(fd, kitty_delete(img.image_id))
            finally:
                os.close(fd)
        except OSError as e:
            self.fail(f"fullscreen stumbled ({e})")
        finally:
            art.tui_resume()

    def save_page(self) -> None:
        tab = self.tab
        if tab.page is None:
            return
        text = "\n".join(line.plain() for line in tab.page.lines)
        dest = Path.home() / "Downloads" / (safe_filename(tab.url) + ".txt")
        try:
            dest.write_text(f"{tab.title}\n{tab.url}\n\n{text}\n", encoding="utf-8")
            self.flash = f"saved {dest.name}"
        except OSError as e:
            self.fail(f"could not save ({e})")


def _escape(text: str) -> str:
    import html as _h
    return _h.escape(text or "", quote=True)


def _suffix_for(resp: Response) -> str:
    ct = resp.content_type.lower()
    table = {
        "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
        "image/webp": ".webp", "image/bmp": ".bmp", "video/mp4": ".mp4",
        "video/webm": ".webm", "audio/mpeg": ".mp3", "audio/ogg": ".ogg",
        "audio/wav": ".wav",
    }
    if ct in table:
        return table[ct]
    suffix = Path(urllib.parse.urlparse(resp.url).path).suffix
    return suffix if len(suffix) <= 5 else ".bin"


def _ansi_for(color: CSSColor, background: bool, truecolor: bool) -> str:
    r, g, b = color.rgb()
    if truecolor:
        return f"\x1b[{48 if background else 38};2;{r};{g};{b}m"
    from magpie_image import rgb_to_ansi256
    return f"\x1b[{48 if background else 38};5;{rgb_to_ansi256(r, g, b)}m"


def browse_main(argv: list[str]) -> int:
    import argparse
    import magpie_config as cfg
    ap = argparse.ArgumentParser(prog="magpie browse", description="Magpie TUI browser")
    ap.add_argument("url", nargs="*", default=[])
    ap.add_argument("--tor", action="store_true", default=None)
    ap.add_argument("--no-tor", action="store_true")
    ap.add_argument("--js", choices=("on", "off", "ask"), default=None)
    ap.add_argument("--dump", action="store_true", help="print page text, no TUI")
    ap.add_argument("--no-wizard", action="store_true", help="skip the first-run setup offer")
    args = ap.parse_args(argv)
    start = " ".join(args.url).strip()
    if args.dump:
        return dump_main(start or "magpie:start", tor=args.tor)
    cfgv = cfg.effective()
    tor = bool(args.tor) or (bool(cfgv["search.tor"]) and not args.no_tor)
    js_mode = args.js or str(cfgv["browse.js"])
    browser = Browser(tor=tor, js_mode=js_mode)
    browser.tor_locked = args.tor is not None or args.no_tor
    browser.js_locked = args.js is not None
    return browser.run(start, no_wizard=args.no_wizard)


def dump_main(url: str, *, tor: bool = False) -> int:
    if url.startswith("magpie:"):
        print("magpie: internal pages need the TUI (run without --dump)", file=sys.stderr)
        return 2
    try:
        url = normalize_url(url)
    except FetchError:
        return dump_search(url, tor=tor)
    client = HttpClient(tor=tor)
    try:
        if url.startswith("file:"):
            resp = read_local_file(url)
        else:
            resp = client.request(url, top_level=True)
    except FetchError as e:
        print(f"magpie: {e}", file=sys.stderr)
        return 1
    kind = sniff_kind(resp.data, resp.content_type)
    if kind == "html":
        page = build_page(resp.url, resp.text(), 100)
        for line in page.lines:
            print(line.plain().rstrip())
        return 0
    if kind == "text":
        print(resp.text())
        return 0
    print(f"magpie: {kind} ({len(resp.data)} bytes): {resp.url}", file=sys.stderr)
    return 0


def dump_search(query: str, *, tor: bool = False) -> int:
    """--dump with search words: print quiet-web results as text."""
    try:
        legacy = legacy_magpie()
    except (ImportError, OSError) as e:
        print(f"magpie: {e}", file=sys.stderr)
        return 2
    try:
        results, eng, err = legacy.search_chain(query, n=10, tor=tor, page=1)
    except (ValueError, RuntimeError, OSError) as e:
        print(f"magpie: search stumbled ({e})", file=sys.stderr)
        return 1
    if not results:
        print(f"magpie: {err or 'no results'}", file=sys.stderr)
        return 1
    print(f"# {query}  (via {eng})")
    for i, r in enumerate(results, 1):
        title = (r.get("title") or "(no title)").strip()
        snip = (r.get("abstract") or "").strip()[:280]
        print(f"\n{i}. {title}")
        if snip and snip.lower() != title.lower():
            print(f"   {snip}")
    return 0
