#!/usr/bin/env python3
"""ia — shared wave to the Internet Archive free media (used by `siren trove`).

Legal free media engine: search, list, interactive pick, download.
Moved out of `ether` (which is networking only now).
"""
from __future__ import annotations

import os
import re
import sys
import time
import urllib.error  # noqa: F401
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path.home() / "bin"))
import pixie_termart as art  # noqa: E402

os.environ.setdefault("PIXIE_UNICODE", "1")

UA = "siren-trove/1.0 (legal archive.org client; +https://archive.org)"
IA_SEARCH = "https://archive.org/advancedsearch.php"
IA_META = "https://archive.org/metadata/{ident}"
IA_DOWNLOAD = "https://archive.org/download/{ident}/{name}"

AUDIO_DIR = Path(os.environ.get("TROVE_AUDIO_DIR", Path.home() / "Music" / "trove"))
VIDEO_DIR = Path(os.environ.get("TROVE_VIDEO_DIR", Path.home() / "Videos" / "trove"))

BRAND = "siren trove"

KIND_MAP: dict[str, dict[str, str]] = {
    "music": {
        "mediatype": "audio",
        "hint": "(subject:(music) OR collection:(opensource_audio) OR collection:(netlabels))",
    },
    "tracks": {"mediatype": "audio", "hint": "(subject:(music) OR collection:(opensource_audio))"},
    "songs": {"mediatype": "audio", "hint": "(subject:(music) OR collection:(opensource_audio))"},
    "album": {
        "mediatype": "audio",
        "hint": "(subject:(album) OR subject:(music) OR collection:(netlabels))",
    },
    "podcast": {
        "mediatype": "audio",
        "hint": "(subject:(podcast) OR collection:(podcasts) OR title:(podcast))",
    },
    "podcasts": {
        "mediatype": "audio",
        "hint": "(subject:(podcast) OR collection:(podcasts) OR title:(podcast))",
    },
    "shows": {
        "mediatype": "audio",
        "hint": "(subject:(podcast) OR collection:(podcasts) OR title:(podcast))",
    },
    "audiobook": {
        "mediatype": "audio",
        "hint": "(collection:(librivoxaudio) OR subject:(audiobook) OR creator:(LibriVox))",
    },
    "audiobooks": {
        "mediatype": "audio",
        "hint": "(collection:(librivoxaudio) OR subject:(audiobook) OR creator:(LibriVox))",
    },
    "movie": {
        "mediatype": "movies",
        "hint": "(subject:(feature) OR subject:(film) OR collection:(feature_films))",
    },
    "movies": {
        "mediatype": "movies",
        "hint": "(subject:(feature) OR collection:(feature_films))",
    },
    "films": {
        "mediatype": "movies",
        "hint": "(subject:(film) OR collection:(feature_films))",
    },
    "series": {
        "mediatype": "movies",
        "hint": "(subject:(series) OR subject:(television) OR subject:(episode))",
    },
    "video": {
        "mediatype": "movies",
        "hint": "",
    },
    "documentary": {
        "mediatype": "movies",
        "hint": "(subject:(documentary) OR collection:(documentary))",
    },
    "documentaries": {
        "mediatype": "movies",
        "hint": "(subject:(documentary) OR collection:(documentary))",
    },
}

KIND_TOKENS = set(KIND_MAP) | {"audio", "films"}


def eprint(*a: Any, **k: Any) -> None:
    print(*a, file=sys.stderr, **k)


def paint(s: str, *styles: str) -> str:
    return art.paint(s, *styles)


def seg(*pieces: tuple[str, tuple[str, ...]]) -> str:
    """Join pre-painted pieces into one visible row (colors survive framing)."""
    return "".join(paint(t, *st) for t, st in pieces)


def _trove_frame(
    lines: list[str],
    *,
    title: str,
    subtitle: str = "",
    width: int | None = None,
) -> str:
    """Hand-drawn pink frame that keeps per-row colors (art.box repaints)."""
    unicode_mode = art.strip_ansi(os.environ.get("PIXIE_UNICODE", "")).lower() in (
        "1", "on", "true", "yes", "unicode",
    )
    tl, tr, bl, br, hz, vt = ("╭", "╮", "╰", "╯", "─", "│") if unicode_mode else ("+", "+", "+", "+", "-", "|")
    mark = "✦" if unicode_mode else "*"
    w = width or art.term_width()
    outer = max(36, min(w, 96))
    inner = outer - 2
    body_w = inner - 2
    out = []
    if title:
        tplain = art.strip_ansi(title)
        label = f" {mark} {tplain} "
        fill = max(0, inner - art.vis_len(label) - 1)
        out.append(paint(tl + hz, art.P.PINK_DIM) + paint(label, art.P.BOLD, art.P.PINK) + paint(hz * fill + tr, art.P.PINK_DIM))
    else:
        out.append(paint(tl + hz * inner + tr, art.P.PINK_DIM))
    if subtitle:
        for ln in art.wrap_plain(art.strip_ansi(subtitle), body_w):
            out.append(paint(vt + " " + art.pad_vis(ln, body_w) + " " + vt, art.P.MUTED))
        out.append(paint(vt + " " + ("·" if unicode_mode else "-") * body_w + " " + vt, art.P.PINK_DIM))
    for line in lines:
        pad = max(0, body_w - art.vis_len(art.strip_ansi(line)))
        out.append(paint(vt, art.P.PINK_DIM) + " " + line + " " * pad + " " + paint(vt, art.P.PINK_DIM))
    out.append(paint(bl + hz * inner + br, art.P.PINK_DIM))
    return "\n".join(out)


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


MAX_TOTAL = int(os.environ.get("TROVE_MAX_TOTAL", "0") or 0)
NO_CONFIRM = os.environ.get("TROVE_NO_CONFIRM", "") in ("1", "yes", "true", "on")


def http_json(url: str, timeout: float = 12) -> dict:
    """JSON GET with a tight timeout (IA is usually <2s when healthy)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(4_000_000)
        return json_loads(raw.decode())


def json_loads(raw: str) -> dict:
    import json

    return json.loads(raw)


def build_query(kind: str | None, terms: list[str]) -> str:
    """Build IA lucene-ish query from kind + free text."""
    parts: list[str] = []
    k = (kind or "").lower().strip()
    if k in KIND_MAP:
        parts.append(f"mediatype:({KIND_MAP[k]['mediatype']})")
        hint = KIND_MAP[k].get("hint") or ""
        if hint:
            parts.append(hint)
    elif k in ("audio",):
        parts.append("mediatype:(audio)")
    elif k in ("movies", "films"):
        parts.append("mediatype:(movies)")
    words = [t for t in terms if t]
    if kind and kind.lower() not in KIND_TOKENS:
        words = [kind] + words
    if words:
        qtext = " ".join(words)
        esc = qtext.replace('"', " ")
        parts.append(
            f'(title:({esc}) OR subject:({esc}) OR description:({esc}) OR creator:({esc}))'
        )
    if not parts:
        parts.append("mediatype:(audio)")
    return " AND ".join(parts)


def search(query: str, rows: int = 10, page: int = 1) -> tuple[list[dict], int]:
    rows = max(1, min(int(rows), 50))
    page = max(1, int(page))
    q = urllib.parse.urlencode(
        {"q": query, "rows": rows, "page": page, "output": "json", "sort[]": "downloads desc"}
    )
    for fl in ("identifier", "title", "creator", "year", "mediatype", "downloads"):
        q += f"&fl[]={fl}"
    data = http_json(f"{IA_SEARCH}?{q}")
    resp = data.get("response") or {}
    docs = resp.get("docs") or []
    n = int(resp.get("numFound") or 0)
    return docs, n


def fmt_item(i: int, doc: dict) -> list[str]:
    """Two painted lines for one search hit: title row + metadata row."""
    title = doc.get("title") or doc.get("identifier") or "?"
    if isinstance(title, list):
        title = title[0]
    creator = doc.get("creator") or ""
    if isinstance(creator, list):
        creator = ", ".join(creator[:2])
    year = doc.get("year") or ""
    if isinstance(year, list):
        year = year[0]
    mt = doc.get("mediatype") or ""
    if isinstance(mt, list):
        mt = mt[0]
    ident = doc.get("identifier") or ""
    dl = doc.get("downloads") or ""
    meta = " · ".join(
        x for x in (str(creator)[:40], str(year), str(mt), f"↓{dl}" if dl != "" else "") if x
    )
    return [
        seg(
            (f"{i:>2}.", (art.P.BOLD, art.P.PINK)),
            ("  " + str(title)[:68], (art.P.SILVER,)),
        ),
        seg(
            ("    " + meta, (art.P.MUTED,)),
            ("  " + ident, (art.P.PINK_DIM,)),
        ),
    ]


def item_meta(ident: str) -> dict:
    """Raw metadata root for an identifier (includes 'files' + 'mediatype')."""
    return http_json(IA_META.format(ident=urllib.parse.quote(ident)))


def list_files(ident: str) -> list[dict]:
    meta = item_meta(ident)
    files = meta.get("files") or []
    audio_ext = {".mp3", ".ogg", ".flac", ".m4a", ".wav", ".opus"}
    video_ext = {".mp4", ".mkv", ".webm", ".avi", ".ogv", ".mov"}
    out = []
    for f in files:
        name = f.get("name") or ""
        if name.endswith(".xml") or name.endswith(".sqlite") or "/." in name:
            continue
        low = name.lower()
        ext = Path(low).suffix
        if ext in audio_ext or ext in video_ext:
            out.append(f)

    def score(f: dict) -> tuple:
        name = (f.get("name") or "").lower()
        ext = Path(name).suffix
        prefer = 0 if ext in {".mp3", ".ogg", ".mp4", ".mkv", ".flac"} else 1
        try:
            sz = int(f.get("size") or 0)
        except ValueError:
            sz = 0
        return (prefer, -sz)

    out.sort(key=score)
    return out


def pick_download_targets(ident: str, mediatype: str = "") -> list[tuple[str, str, Path, int]]:
    """(url, filename, dest_dir, size) — video decided by mediatype, not one stray file."""
    meta = item_meta(ident)
    files = meta.get("files") or []
    mt = (mediatype or "").lower() or str(meta.get("mediatype") or "").lower()
    audio_ext = {".mp3", ".ogg", ".flac", ".m4a", ".wav", ".opus"}
    video_ext = {".mp4", ".mkv", ".webm", ".avi", ".ogv", ".mov"}
    media = [f for f in files if Path((f.get("name") or "").lower()).suffix in audio_ext | video_ext]
    if not media:
        return []
    is_video = mt.startswith("movie")
    if not is_video and not any(Path((f.get("name") or "").lower()).suffix in audio_ext for f in media):
        is_video = True
    dest_root = VIDEO_DIR if is_video else AUDIO_DIR
    dest_dir = dest_root / re.sub(r"[^\w.\-]+", "_", ident)[:80]
    media = media[:1] if is_video else media[:40]
    targets: list[tuple[str, str, Path, int]] = []
    for f in media:
        name = f["name"]
        base = Path(name).name
        url = IA_DOWNLOAD.format(ident=urllib.parse.quote(ident), name=urllib.parse.quote(name, safe="/"))
        try:
            size = int(f.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        targets.append((url, base, dest_dir, size))
    return targets


def _stream_download(url: str, dest: Path) -> bool:
    """Python downloader — one live progress line (no curl spam), resume, Ctrl-C cleans up."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = Path(str(dest) + ".part")
    cur = part.stat().st_size if part.exists() else 0
    try:
        headers = {"User-Agent": UA}
        if cur:
            headers["Range"] = f"bytes={cur}-"
        req = urllib.request.Request(url, headers=headers)
        total = None
        with urllib.request.urlopen(req, timeout=30) as r:
            try:
                total = int(r.headers.get("Content-Length") or 0) + cur
            except ValueError:
                total = None
            tty = sys.stderr.isatty()
            t0 = time.time()
            with open(part, "ab" if cur else "wb") as fh:
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    fh.write(chunk)
                    cur += len(chunk)
                    if tty and total:
                        frac = min(1.0, cur / max(total, 1))
                        rate = cur / max(0.001, time.time() - t0) / 1024
                        eprint(
                            f"\r\033[2K  ↓ {dest.name[:44]:<44} {frac:>4.0%}  {_fmt_size(cur)}"
                            f"/{_fmt_size(total)}  {rate:.0f} kB/s",
                            end="",
                        )
                    elif tty and cur == 0:
                        eprint(f"\r\033[2K  ↓ {dest.name}", end="")
        if tty and not sys.stderr.isatty():
            pass
        elif tty:
            eprint()
        part.rename(dest)
    except urllib.error.URLError as e:
        if part.exists() and part.stat().st_size == 0:
            part.unlink(missing_ok=True)
        eprint()
        eprint(paint(f"  download failed ({getattr(e, 'reason', e)}): {dest.name}", art.P.WARN))
        return 1
    except (OSError, KeyboardInterrupt):
        eprint("\n  interrupted — partial kept as {dest.name}.part".replace("{dest.name}", dest.name))
        return 1
    return 0


def download_file(url: str, dest: Path, size: int = 0) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        eprint(paint(f"  skip (exists): {dest.name}", art.P.MUTED))
        return True
    eprint(paint(f"  ↓ {dest.name}  {_fmt_size(size) if size else '…'}", art.P.PINK))
    return _stream_download(url, dest) == 0


def _confirm(prompt: str, default: bool = True) -> bool:
    if NO_CONFIRM:
        return True
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        ans = input(paint(prompt + suffix, art.P.MUTED)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not ans:
        return default
    return ans.startswith("y")


def do_download(doc: dict) -> None:
    ident = doc.get("identifier") or ""
    mt = doc.get("mediatype") or ""
    if isinstance(mt, list):
        mt = mt[0]
    title = doc.get("title") or ident
    if isinstance(title, list):
        title = title[0]
    eprint(paint(f"Fetching file list for {ident} …", art.P.PINK_DIM))
    try:
        targets = pick_download_targets(ident, str(mt))
    except Exception as e:
        eprint(paint(f"metadata error: {e}", art.P.WARN))
        return
    if not targets:
        eprint(paint("No audio/video files found on this item (metadata only?).", art.P.WARN))
        eprint(f"  Browse: https://archive.org/details/{ident}")
        return
    total = sum(t[3] for t in targets)
    dest_dir = targets[0][2]
    label = f"{len(targets)} file(s) · {_fmt_size(total)} → {dest_dir}"
    if MAX_TOTAL and total > MAX_TOTAL:
        eprint(paint(
            f"  refusing: {_fmt_size(total)} exceeds TROVE_MAX_TOTAL={_fmt_size(MAX_TOTAL)}",
            art.P.WARN,
        ))
        eprint(paint(f"  set TROVE_MAX_TOTAL or pick a smaller item.", art.P.MUTED))
        return
    if len(targets) > 1 or total > 32 * 1024 * 1024:
        if not _confirm(f"Download {label}?", default=False):
            eprint("  skipped.")
            return
    eprint(paint(f"Downloading {label}", art.P.OK))
    ok = 0
    try:
        for url, name, ddir, size in targets:
            if download_file(url, ddir / name, size):
                ok += 1
    except KeyboardInterrupt:
        eprint(paint("  interrupted.", art.P.WARN))
    eprint(paint(f"Done: {ok}/{len(targets)}  ({title})", art.P.OK))


def interactive_list(
    docs: list[dict],
    num_found: int,
    query: str,
    *,
    brand: str = BRAND,
) -> str:
    """Returns: quit | again | or empty after downloads."""
    tw = art.term_width()
    body_w = max(36, min(tw, 96)) - 4
    ql = art.wrap_plain(query, body_w - 10) or [query]
    lines: list[str] = []
    for j, part in enumerate(ql):
        lines.append(paint(("query:   " if j == 0 else "         ") + part, art.P.MUTED))
    lines.append(paint(f"matches: {num_found:,}  ·  showing {len(docs)}", art.P.MUTED))
    lines.append("")
    if not docs:
        print()
        print(_trove_frame(
            lines + [paint("No results. Try different words.", art.P.WARN)],
            title=f"{brand} ✦",
            subtitle="free & legal media (Internet Archive)",
            width=tw,
        ))
        print()
        return "again"
    for i, d in enumerate(docs, 1):
        lines.extend(fmt_item(i, d))
        lines.append("")
    lines[-1] = paint(
        "  [1-N] download   [a] download all listed   [s] search again   [q] quit",
        art.P.MUTED,
    )
    print()
    print(_trove_frame(lines, title=f"{brand} ✦", subtitle="free & legal media (Internet Archive)", width=tw))
    print()
    while True:
        try:
            choice = input(paint(f"{brand}> ", art.P.PINK)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "quit"
        if choice in ("q", "quit", "exit"):
            return "quit"
        if choice in ("s", "search", "again", "r"):
            return "again"
        if choice in ("a", "all"):
            for d in docs:
                do_download(d)
            print(paint("Done. [s] new search, [q] quit.", art.P.MUTED))
            return ""
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(docs):
                do_download(docs[n - 1])
                print(paint("Another number, [s] search again, or [q] quit?", art.P.MUTED))
                continue
        print(paint("Pick a number, a, s, or q.", art.P.WARN))


def run_trove(n: int = 10, terms: list[str] | None = None, kind: str | None = None) -> int:
    """`siren trove …` — search archive.org, interactively download."""
    terms = list(terms or [])
    n = max(1, min(int(n or 10), 50))
    k = kind
    words = terms
    if not k and words:
        cand = words[0].lower()
        if cand in KIND_TOKENS:
            k = words[0]
            words = words[1:]
    while True:
        query = build_query(k, words)
        eprint(paint(f"  searching archive.org …", art.P.MUTED))
        eprint(paint(f"  q: {query[:120]}{'…' if len(query) > 120 else ''}", art.P.MUTED))
        t0 = time.time()
        try:
            docs, num_found = search(query, rows=n)
        except Exception as e:
            eprint(paint(f"  search failed ({type(e).__name__}): {e}", art.P.WARN))
            eprint(paint("  tip: ether net  checks the weave;  else your hotspot may be down", art.P.MUTED))
            return 1
        eprint(paint(f"  got {len(docs)} hits ({num_found:,} total) in {time.time() - t0:.1f}s", art.P.OK))
        action = interactive_list(docs, num_found, query)
        if action == "quit":
            return 0
        if action == "again":
            try:
                line = input(paint("new search words (or empty to keep): ", art.P.MUTED)).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if line:
                parts = line.split()
                if parts and parts[0].lower() in KIND_TOKENS:
                    k = parts[0]
                    words = parts[1:]
                else:
                    words = parts
            continue
        return 0


def run_get(identifier: str, type_hint: str = "") -> int:
    """Downloadone IA item by identifier."""
    ident = (identifier or "").strip()
    if not ident:
        eprint("usage: siren trove get <identifier>")
        return 2
    doc = {"identifier": ident, "mediatype": type_hint or "", "title": ident}
    try:
        do_download(doc)
    except Exception as e:
        eprint(paint(f"get failed: {e}", art.P.WARN))
        return 1
    return 0