#!/usr/bin/env python3
"""magpie_fetch — network, privacy, history, and media-cache layer for Magpie browse.

This module owns every byte Magpie pulls from the network. It is stdlib-only
and deliberately cookie-safe:

- Cookies live only in memory for one browser session.
- ``--tor`` never silently falls back to clearnet.
- Redirects are followed manually so intermediate cookies/headers are honored.
- Downloads are size-capped and media is content-address cached.

Pages/DOM live in ``magpie_dom``; rendering/TUI live in ``magpie_tui``.
"""
from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import html as html_lib
import json
import os
import re
import shutil
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path


USER_AGENT = "magpie-tui/0.1 (faeOS private browser; cookie-session only)"
MAX_PAGE_BYTES = 3_000_000
MAX_MEDIA_BYTES = 48_000_000
MAX_DOWNLOAD_BYTES = 256_000_000
MAX_INFLATE = 64_000_000
REDIRECT_LIMIT = 6
HISTORY_LIMIT = 5000


class FetchError(Exception):
    """Human-readable network failure (fae voice is added by callers)."""


def cache_dir() -> Path:
    return Path(os.environ.get("MAGPIE_CACHE", str(Path.home() / ".cache" / "magpie")))


def config_dir() -> Path:
    return Path(os.environ.get("MAGPIE_CONFIG", str(Path.home() / ".config" / "magpie")))


def ensure_dirs() -> tuple[Path, Path]:
    c = cache_dir()
    g = config_dir()
    (c / "media").mkdir(parents=True, exist_ok=True)
    (c / "pages").mkdir(parents=True, exist_ok=True)
    g.mkdir(parents=True, exist_ok=True)
    return c, g


def have_tor_support() -> bool:
    return shutil.which("torsocks") is not None


def _host_site(host: str) -> str:
    host = (host or "").lower().rstrip(".")
    if not host:
        return ""
    # IPv4/IPv6 have no registrable suffix handling here; exact host is the site.
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host) or ":" in host:
        return host
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


@dataclass
class Cookie:
    name: str
    value: str
    host: str
    path: str = "/"
    secure: bool = False
    http_only: bool = False
    same_site: str = "lax"
    expires: float = 0.0  # 0 = session cookie

    def expired(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return self.expires > 0 and now >= self.expires

    def matches(self, url: urllib.parse.ParseResult, *, method: str, top_level: bool, now: float) -> bool:
        if self.expired(now):
            return False
        host = (url.hostname or "").lower().rstrip(".")
        if not host:
            return False
        domain = self.host.lower().lstrip(".")
        if host != domain and not host.endswith("." + domain):
            return False
        path = url.path or "/"
        if not path.startswith(self.path):
            return False
        if len(path) > len(self.path) and not self.path.endswith("/") and not path[len(self.path):].startswith("/"):
            return False
        if self.secure and url.scheme != "https":
            return False
        site = _host_site(host)
        cookie_site = _host_site(domain)
        same_site = self.same_site.lower() or "lax"
        if same_site == "strict" and site != cookie_site:
            return False
        if same_site == "lax" and site != cookie_site and not (top_level and method == "GET"):
            return False
        if same_site == "none" and url.scheme != "https":
            return False
        return True


class CookieJar:
    """Ephemeral in-memory cookie jar. Never written to disk."""

    def __init__(self) -> None:
        self._cookies: list[Cookie] = []
        self._lock = threading.RLock()

    def __len__(self) -> int:
        with self._lock:
            self.purge()
            return len(self._cookies)

    def clear(self) -> None:
        with self._lock:
            self._cookies.clear()

    def purge(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._cookies = [c for c in self._cookies if not c.expired(now)]

    def set_from_headers(self, url: str, headers: list[tuple[str, str]]) -> None:
        try:
            parsed = urllib.parse.urlparse(url)
        except ValueError:
            return
        host = (parsed.hostname or "").lower()
        if not host:
            return
        default_path = parsed.path or "/"
        if not default_path.startswith("/"):
            default_path = "/" + default_path
        if "/" in default_path[1:]:
            default_path = default_path.rsplit("/", 1)[0] or "/"
        else:
            default_path = "/"
        now = time.time()
        with self._lock:
            for key, value in headers:
                if key.lower() != "set-cookie":
                    continue
                cookie = parse_set_cookie(value, host, default_path, now)
                if cookie is None:
                    continue
                self._cookies = [
                    c for c in self._cookies
                    if not (c.name == cookie.name and c.host == cookie.host and c.path == cookie.path)
                ]
                if cookie.value == "__magpie_delete__":
                    continue
                self._cookies.append(cookie)
            self.purge(now)

    def header_for(self, url: str, *, method: str = "GET", top_level: bool = True) -> str:
        try:
            parsed = urllib.parse.urlparse(url)
        except ValueError:
            return ""
        now = time.time()
        with self._lock:
            self.purge(now)
            pairs = [
                f"{c.name}={c.value}"
                for c in self._cookies
                if c.matches(parsed, method=method.upper(), top_level=top_level, now=now)
            ]
        return "; ".join(pairs)


def parse_set_cookie(value: str, host: str, default_path: str, now: float) -> Cookie | None:
    parts = [p.strip() for p in value.split(";")]
    if not parts or "=" not in parts[0]:
        return None
    name, val = parts[0].split("=", 1)
    name = name.strip()
    val = val.strip().strip('"')
    if not name or "\n" in name or "\r" in name:
        return None
    cookie = Cookie(name=name, value=val, host=host, path=default_path)
    max_age: float | None = None
    expires: float | None = None
    for attr in parts[1:]:
        if not attr:
            continue
        if "=" in attr:
            k, v = attr.split("=", 1)
            k = k.strip().lower()
            v = v.strip().strip('"')
        else:
            k, v = attr.strip().lower(), ""
        if k == "domain" and v:
            v = v.lower().lstrip(".")
            if host == v or host.endswith("." + v):
                cookie.host = v
        elif k == "path" and v.startswith("/"):
            cookie.path = v
        elif k == "max-age":
            try:
                max_age = float(v)
            except ValueError:
                max_age = None
        elif k == "expires" and v:
            try:
                expires = parsedate_to_datetime(v).timestamp()
            except (TypeError, ValueError, OverflowError):
                expires = None
        elif k == "secure":
            cookie.secure = True
        elif k == "httponly":
            cookie.http_only = True
        elif k == "samesite" and v.lower() in ("lax", "strict", "none"):
            cookie.same_site = v.lower()
    if max_age is not None:
        if max_age <= 0:
            return Cookie(name=name, value="__magpie_delete__", host=cookie.host, path=cookie.path)
        cookie.expires = now + max_age
    elif expires is not None:
        cookie.expires = expires
    return cookie


def normalize_url(text: str, base: str | None = None) -> str:
    text = (text or "").strip()
    if not text:
        raise FetchError("empty address")
    if re.match(r"(?i)^javascript\s*:", text):
        raise FetchError("javascript: addresses are not executed from the address bar")
    if text.startswith("magpie:"):
        return text
    if base:
        try:
            return urllib.parse.urljoin(base, text)
        except ValueError as e:
            raise FetchError(f"bad link: {e}") from e
    if re.match(r"(?i)^[a-z0-9+.-]+://", text):
        return text
    if text.startswith("//"):
        return "https:" + text
    # Host-ish input becomes https; anything else is handled by the caller as search.
    if re.match(r"^(localhost|[\w-]+(\.[\w-]+)+)(:\d+)?(/.*)?$", text):
        return "https://" + text
    raise FetchError(f"not an address: {text!r}")


def resolve_url(base: str, href: str | None) -> str:
    if not href:
        return base
    href = html_lib.unescape(href.strip())
    if re.match(r"(?i)^javascript\s*:", href):
        return base
    try:
        return urllib.parse.urljoin(base, href)
    except ValueError:
        return base


def url_host_label(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().rstrip(".")


def safe_filename(url: str, content_type: str = "", content_disposition: str = "") -> str:
    name = ""
    if content_disposition:
        m = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, re.I)
        if m:
            name = urllib.parse.unquote(m.group(1))
        else:
            m = re.search(r'filename="?([^";]+)"?', content_disposition, re.I)
            if m:
                name = m.group(1)
    if not name:
        try:
            name = Path(urllib.parse.urlparse(url).path).name
        except ValueError:
            name = ""
    name = re.sub(r"[^\w\-. ]+", "_", urllib.parse.unquote(name)).strip(" .") or "download"
    if "." not in Path(name).suffix and content_type:
        ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "application/pdf": ".pdf",
        }.get(content_type.split(";")[0].strip().lower(), "")
        name += ext
    return name[:120]


@dataclass
class Response:
    url: str
    status: int
    headers: list[tuple[str, str]]
    content_type: str
    charset: str
    data: bytes
    chain: list[str] = field(default_factory=list)
    truncated: bool = False

    def header(self, name: str, default: str = "") -> str:
        want = name.lower()
        for k, v in self.headers:
            if k.lower() == want:
                return v
        return default

    def is_html(self) -> bool:
        ct = self.content_type.lower()
        return "html" in ct or "xhtml" in ct

    def is_text(self) -> bool:
        ct = self.content_type.lower()
        return self.is_html() or ct.startswith("text/") or "json" in ct or "xml" in ct

    def text(self) -> str:
        for codec in (self.charset, "utf-8", "windows-1252", "latin-1"):
            if not codec:
                continue
            try:
                return self.data.decode(codec)
            except (LookupError, UnicodeDecodeError):
                continue
        return self.data.decode("utf-8", "replace")

    def kind(self) -> str:
        ct = self.content_type.lower()
        if self.is_html():
            return "html"
        if ct.startswith("image/"):
            return "image"
        if ct.startswith(("video/", "audio/")):
            return "media"
        if ct.startswith("text/") or "json" in ct or "xml" in ct:
            return "text"
        return "file"


def sniff_kind(data: bytes, content_type: str = "") -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct:
        if "html" in ct or "xhtml" in ct:
            return "html"
        if ct.startswith("image/"):
            return "image"
        if ct.startswith(("video/", "audio/")):
            return "media"
        if ct.startswith("text/") or ct.endswith(("+xml", "+json")) or ct in ("application/json", "application/xml"):
            return "text"
    if data.startswith(b"<!doctype html") or data.lstrip()[:15].lower().startswith(b"<!doctype ht"):
        return "html"
    head = data.lstrip()[:64].lower()
    if head.startswith((b"<html", b"<head", b"<!doctype")):
        return "html"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if data.startswith(b"\xff\xd8\xff"):
        return "image"
    if data.startswith((b"GIF87a", b"GIF89a", b"BM")):
        return "image"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image"
    if data.startswith(b"\x1aE\xdf\xa3"):
        return "media"
    if data.startswith(b"ID3") or data.startswith(b"OggS") or data.startswith(b"fLaC"):
        return "media"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "media"
    if data[4:8] == b"ftyp":
        return "media"
    if data.startswith(b"%PDF"):
        return "file"
    return "text" if is_mostly_text(data) else "file"


def is_mostly_text(data: bytes, sample: int = 4096) -> bool:
    if not data:
        return True
    chunk = data[:sample]
    if b"\x00" in chunk:
        return False
    bad = sum(1 for b in chunk if b < 9 or (13 < b < 32 and b != 27))
    return bad / max(1, len(chunk)) < 0.02


class _NoAutoRedirect(urllib.request.HTTPRedirectHandler):
    """Block urllib's built-in redirect following: Magpie walks every hop
    itself so intermediate cookies/headers are honored, never skipped."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpClient:
    def __init__(
        self,
        *,
        tor: bool = False,
        timeout: float = 20.0,
        max_bytes: int = MAX_PAGE_BYTES,
        user_agent: str = USER_AGENT,
        cookies: CookieJar | None = None,
        referer: str = "",
    ) -> None:
        if tor and not have_tor_support():
            raise FetchError("Tor was requested but torsocks is not installed; refusing clearnet")
        self.tor = tor
        self.timeout = max(2.0, float(timeout))
        self.max_bytes = max(1024, int(max_bytes))
        self.user_agent = user_agent
        self.cookies = cookies or CookieJar()
        self.referer = referer
        ctx = ssl.create_default_context()
        # Plain opener: default redirect handlers are intentionally absent so
        # every hop is followed manually (cookies + loop safety).
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPHandler(),
            urllib.request.HTTPSHandler(context=ctx),
            _NoAutoRedirect(),
        )

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str = "",
        top_level: bool = True,
        site_hint: str = "",
        max_bytes: int | None = None,
    ) -> Response:
        method = method.upper()
        cap = max(1024, int(max_bytes)) if max_bytes else self.max_bytes
        chain = [url]
        current = url
        payload = body
        ctype = content_type
        for _ in range(REDIRECT_LIMIT + 1):
            req = self._make_request(current, method, payload, ctype, top_level, site_hint)
            try:
                with self._opener.open(req, timeout=self.timeout) as resp:
                    status = getattr(resp, "status", 200) or 200
                    headers = [(k, v) for k, v in resp.getheaders()]
                    self.cookies.set_from_headers(current, headers)
                    if status in (301, 302, 303, 307, 308):
                        nxt = self._redirect_target(current, status, headers)
                        if not nxt:
                            raise FetchError(f"redirect {status} without a location")
                        if nxt in chain:
                            raise FetchError("redirect loop detected")
                        chain.append(nxt)
                        if status == 303 or (status in (301, 302) and method == "POST"):
                            method, payload, ctype = "GET", None, ""
                        current = nxt
                        top_level = True
                        continue
                    data, truncated = self._read_capped(resp, cap)
                    data = self._decode_body(headers, data)
                    ct, charset = parse_content_type(dict(headers).get("Content-Type", ""))
                    return Response(
                        url=current,
                        status=status,
                        headers=headers,
                        content_type=ct,
                        charset=charset,
                        data=data,
                        chain=chain,
                        truncated=truncated,
                    )
            except urllib.error.HTTPError as e:
                headers = [(k, v) for k, v in (e.headers.items() if e.headers else [])]
                self.cookies.set_from_headers(current, headers)
                if e.code in (301, 302, 303, 307, 308):
                    nxt = self._redirect_target(current, e.code, headers)
                    try:
                        e.close()
                    except OSError:
                        pass
                    if not nxt:
                        raise FetchError(f"redirect {e.code} without a location") from e
                    if nxt in chain:
                        raise FetchError("redirect loop detected") from e
                    chain.append(nxt)
                    if e.code == 303 or (e.code in (301, 302) and method == "POST"):
                        method, payload, ctype = "GET", None, ""
                    current = nxt
                    top_level = True
                    continue
                data, truncated = self._read_error_body(e, cap)
                ct, charset = parse_content_type(dict(headers).get("Content-Type", ""))
                return Response(
                    url=current,
                    status=e.code or 0,
                    headers=headers,
                    content_type=ct,
                    charset=charset,
                    data=data,
                    chain=chain,
                    truncated=truncated,
                )
            except urllib.error.URLError as e:
                raise FetchError(f"could not reach {url_host_label(current) or current}: {e.reason}") from e
            except (ssl.SSLError, OSError) as e:
                raise FetchError(f"network trouble reaching {url_host_label(current) or current}: {e}") from e
        raise FetchError("too many redirects")

    def _make_request(
        self, url: str, method: str, body: bytes | None, ctype: str, top_level: bool, site_hint: str
    ) -> urllib.request.Request:
        scheme = urllib.parse.urlparse(url).scheme.lower()
        if scheme not in ("http", "https"):
            raise FetchError(f"unsupported address scheme: {scheme or '(none)'}")
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,image/*,video/*,audio/*;q=0.9,*/*;q=0.5",
            "Accept-Language": "en-US,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close",
        }
        cookie = self.cookies.header_for(url, method=method, top_level=top_level)
        if cookie:
            headers["Cookie"] = cookie
        if self.referer and top_level and site_hint and _host_site(url_host_label(url)) == _host_site(url_host_label(site_hint)):
            headers["Referer"] = site_hint
        if body is not None:
            headers["Content-Type"] = ctype or "application/x-www-form-urlencoded"
            headers["Content-Length"] = str(len(body))
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        if self.tor:
            # torsocks path: curl speaks through Tor; urllib stays clearnet-free.
            raise FetchError("Tor HTTP is not wired into the streaming client yet; use search --tor")
        return req

    @staticmethod
    def _redirect_target(current: str, status: int, headers: list[tuple[str, str]]) -> str:
        loc = ""
        for k, v in headers:
            if k.lower() == "location":
                loc = v.strip()
                break
        if not loc:
            return ""
        nxt = resolve_url(current, loc)
        if urllib.parse.urlparse(nxt).scheme.lower() not in ("http", "https"):
            raise FetchError(f"redirect {status} points outside http(s)")
        return nxt

    def _read_capped(self, resp, cap: int) -> tuple[bytes, bool]:
        buf = bytearray()
        limit = cap + 1
        try:
            while len(buf) <= cap:
                chunk = resp.read(min(65536, limit - len(buf)))
                if not chunk:
                    break
                buf.extend(chunk)
        except (OSError, ValueError) as e:
            raise FetchError(f"interrupted download: {e}") from e
        if len(buf) > cap:
            return bytes(buf[:cap]), True
        return bytes(buf), False

    def _read_error_body(self, err: urllib.error.HTTPError, cap: int) -> tuple[bytes, bool]:
        try:
            data = err.read(cap + 1)
        except OSError:
            return b"", False
        if len(data) > cap:
            return data[:cap], True
        return data, False

    @staticmethod
    def _decode_body(headers: list[tuple[str, str]], data: bytes) -> bytes:
        enc = ""
        for k, v in headers:
            if k.lower() == "content-encoding":
                enc = v.strip().lower()
                break
        if not enc or enc == "identity":
            return data
        # Inflation cap: compressed replies must stay modest in memory.
        try:
            if enc == "gzip":
                d = zlib.decompressobj(31)
            elif enc == "deflate":
                d = zlib.decompressobj()
            else:
                raise FetchError(f"unsupported reply encoding: {enc}")
            out = d.decompress(data, MAX_INFLATE + 1)
            out += d.flush(max(0, MAX_INFLATE + 1 - len(out)))
        except (OSError, zlib.error, ValueError) as e:
            raise FetchError(f"compressed reply would not unpack ({enc}): {e}") from e
        if len(out) > MAX_INFLATE:
            raise FetchError(f"compressed reply inflates past the {MAX_INFLATE // 1024 // 1024} MiB cap")
        if enc == "deflate" and not out:
            # Raw deflate streams (no zlib wrapper) need a second chance.
            try:
                d = zlib.decompressobj(-zlib.MAX_WBITS)
                out = d.decompress(data, MAX_INFLATE + 1)
                out += d.flush(max(0, MAX_INFLATE + 1 - len(out)))
            except (OSError, zlib.error, ValueError) as e:
                raise FetchError(f"compressed reply would not unpack ({enc}): {e}") from e
            if len(out) > MAX_INFLATE:
                raise FetchError(f"compressed reply inflates past the {MAX_INFLATE // 1024 // 1024} MiB cap")
        return out


def parse_content_type(value: str) -> tuple[str, str]:
    value = (value or "").strip()
    if not value:
        return "", ""
    parts = [p.strip() for p in value.split(";")]
    ct = parts[0].lower()
    charset = ""
    for p in parts[1:]:
        if p.lower().startswith("charset="):
            charset = p.split("=", 1)[1].strip().strip('"').lower()
    return ct, charset


def parse_data_url(url: str, *, limit: int = MAX_MEDIA_BYTES) -> Response:
    try:
        scheme, rest = url.split(":", 1)
    except ValueError as e:
        raise FetchError("bad data: address") from e
    if scheme.lower() != "data":
        raise FetchError("not a data: address")
    meta, _, payload = rest.partition(",")
    is_b64 = meta.strip().endswith(";base64")
    mime = meta[: -len(";base64")] if is_b64 else meta
    mime = mime.strip() or "text/plain;charset=US-ASCII"
    try:
        data = base64.b64decode(payload, validate=False) if is_b64 else urllib.parse.unquote_to_bytes(payload)
    except (binascii.Error, ValueError) as e:
        raise FetchError(f"bad data: payload: {e}") from e
    if len(data) > limit:
        raise FetchError("data: payload is larger than the media cap")
    ct, charset = parse_content_type(mime)
    return Response(url=url, status=200, headers=[], content_type=ct, charset=charset, data=data, chain=[url])


def read_local_file(url: str, *, limit: int = MAX_PAGE_BYTES) -> Response:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "file":
        raise FetchError("not a file: address")
    path = Path(urllib.parse.unquote(parsed.path))
    if not path.is_file():
        raise FetchError(f"local file not found: {path}")
    try:
        if path.stat().st_size > limit:
            raise FetchError("local file is larger than the page cap")
        data = path.read_bytes()
    except OSError as e:
        raise FetchError(f"could not read {path}: {e}") from e
    suffix = path.suffix.lower()
    ct = {
        ".html": "text/html", ".htm": "text/html", ".xhtml": "application/xhtml+xml",
        ".txt": "text/plain", ".md": "text/markdown", ".json": "application/json",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
        ".mp4": "video/mp4", ".webm": "video/webm", ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg", ".wav": "audio/wav",
    }.get(suffix, "")
    return Response(url=url, status=200, headers=[], content_type=ct, charset="utf-8", data=data, chain=[url])


@dataclass
class HistoryEntry:
    url: str
    title: str
    ts: float


def history_path() -> Path:
    ensure_dirs()
    return cache_dir() / "history.jsonl"


def load_history(limit: int = 500) -> list[HistoryEntry]:
    path = history_path()
    rows: list[HistoryEntry] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-max(1, limit * 2):]:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            rows.append(HistoryEntry(url=str(rec.get("url", "")), title=str(rec.get("title", "")), ts=float(rec.get("ts", 0))))
        except (ValueError, TypeError):
            continue
    seen: set[str] = set()
    out: list[HistoryEntry] = []
    for row in reversed(rows):
        if not row.url or row.url in seen:
            continue
        seen.add(row.url)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def record_history(url: str, title: str = "") -> None:
    if not url or url.startswith(("magpie:", "about:")):
        return
    path = history_path()
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"url": url, "title": title[:200], "ts": time.time()}, ensure_ascii=False) + "\n")
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > HISTORY_LIMIT:
            path.write_text("\n".join(lines[-HISTORY_LIMIT:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def clear_history() -> None:
    try:
        history_path().unlink(missing_ok=True)
    except OSError:
        pass


def bookmarks_path() -> Path:
    ensure_dirs()
    return config_dir() / "bookmarks.json"


def load_bookmarks() -> list[dict[str, str]]:
    path = bookmarks_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = []
    out = []
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and row.get("url"):
                out.append({"title": str(row.get("title") or row["url"]), "url": str(row["url"])})
    return out


def save_bookmarks(rows: list[dict[str, str]]) -> None:
    ensure_dirs()
    clean = [{"title": r.get("title", r.get("url", "")), "url": r.get("url", "")} for r in rows if r.get("url")]
    tmp = bookmarks_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(bookmarks_path())


def import_lynx_bookmarks(path: str | Path | None = None) -> list[dict[str, str]]:
    src = Path(path).expanduser() if path else Path.home() / "lynx_bookmarks.html"
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise FetchError(f"lynx bookmarks not readable: {e}") from e
    rows: list[dict[str, str]] = []
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, re.I | re.S):
        href = html_lib.unescape(m.group(1)).strip()
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if not href or href.lower().startswith(("javascript:", "mailto:")):
            continue
        rows.append({"title": title or href, "url": href})
    if not rows:
        raise FetchError("no links found in lynx bookmarks")
    return rows


def media_cache_path(digest: str, suffix: str) -> Path:
    ensure_dirs()
    return cache_dir() / "media" / f"{digest}{suffix}"


def cache_media_bytes(data: bytes, suffix: str = ".bin") -> Path:
    if not suffix.startswith("."):
        suffix = "." + suffix
    digest = hashlib.sha256(data).hexdigest()
    path = media_cache_path(digest, suffix)
    if not path.is_file():
        path.write_bytes(data)
    prune_media_cache()
    return path


def prune_media_cache(limit_bytes: int = 256 * 1024 * 1024) -> None:
    root = cache_dir() / "media"
    try:
        files = [(p.stat().st_mtime, p.stat().st_size, p) for p in root.glob("*") if p.is_file()]
    except OSError:
        return
    total = sum(s for _, s, _ in files)
    if total <= limit_bytes:
        return
    for _, _, p in sorted(files):
        try:
            total -= p.stat().st_size
            p.unlink()
        except OSError:
            continue
        if total <= limit_bytes:
            break


def download_to_downloads(response: Response, *, filename: str = "") -> Path:
    dest_dir = Path.home() / "Downloads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = filename or safe_filename(response.url, response.content_type, response.header("Content-Disposition"))
    dest = dest_dir / name
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        for i in range(2, 1000):
            cand = dest_dir / f"{stem}-{i}{suffix}"
            if not cand.exists():
                dest = cand
                break
    if len(response.data) > MAX_DOWNLOAD_BYTES:
        raise FetchError("file is larger than the download cap")
    dest.write_bytes(response.data)
    return dest


def run_capture(cmd: list[str], *, timeout: float) -> tuple[int, bytes, str]:
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except FileNotFoundError:
        return 127, b"", "not installed"
    except subprocess.TimeoutExpired:
        return 124, b"", "timed out"
    except OSError as e:
        return 127, b"", str(e)
    return proc.returncode, proc.stdout, proc.stderr.decode("utf-8", "replace")
