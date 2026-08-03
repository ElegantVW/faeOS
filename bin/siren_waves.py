#!/usr/bin/env python3
"""Siren open waves — ASCII spectrum EQ for the TUI.

Format rules (kmscon-hardened):
  - ASCII only (# - | + and spaces) for the bars themselves
  - Color via shared pixie_termart (optional; safe if NO_COLOR)
  - No wide glyphs; fixed column widths

Data:
  1) Real: short ffmpeg slice at mpv time-pos → pure-Python FFT → bands
  2) Fallback: smooth reactive animation when sample fails / silence
"""
from __future__ import annotations

import math
import os
import struct
import subprocess
import time
from pathlib import Path
from typing import Sequence

# ── palette (256-color; baby blue + rose) ─────────────────────────────
ROSE = "\033[38;5;175m"
ROSE_DIM = "\033[38;5;132m"
BLUE = "\033[38;5;117m"
BLUE_DIM = "\033[38;5;74m"
SILVER = "\033[38;5;252m"
MUTED = "\033[38;5;245m"
RESET = "\033[0m"
BOLD = "\033[1m"

# sampler
_SR = 11025  # low rate = fast slice
_N = 512  # power of 2
_SAMPLE_SECS = _N / _SR

# smoothed state (module-level so UI can call each frame)
_levels: list[float] = []
_last_sample_t = 0.0
_last_path = ""
_last_pos = -1.0
_source = "idle"  # idle | live | fall


def _color_ok() -> bool:
    if os.environ.get("NO_COLOR", "").strip():
        return False
    try:
        import sys
        from pathlib import Path as _P

        if str(_P.home() / "bin") not in sys.path:
            sys.path.insert(0, str(_P.home() / "bin"))
        import pixie_termart as art  # type: ignore

        return bool(art.color_ok())
    except Exception:
        try:
            return os.isatty(1)
        except Exception:
            return False


def _paint(s: str, *codes: str) -> str:
    if not _color_ok() or not codes:
        return s
    return "".join(codes) + s + RESET


def _fft_mags(real: list[float]) -> list[float]:
    """Radix-2 Cooley–Tukey FFT magnitude spectrum (real input)."""
    n = len(real)
    if n == 0 or n & (n - 1):
        # pad / trim to power of 2
        p = 1
        while p < max(1, n):
            p <<= 1
        real = (real + [0.0] * p)[:p]
        n = p
    # bit-reverse
    j = 0
    re = list(real)
    im = [0.0] * n
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            re[i], re[j] = re[j], re[i]
            im[i], im[j] = im[j], im[i]
    length = 2
    while length <= n:
        ang = -2.0 * math.pi / length
        wlen_r = math.cos(ang)
        wlen_i = math.sin(ang)
        for i0 in range(0, n, length):
            wr, wi = 1.0, 0.0
            half = length // 2
            for k in range(half):
                u_r = re[i0 + k]
                u_i = im[i0 + k]
                v_r = re[i0 + k + half] * wr - im[i0 + k + half] * wi
                v_i = re[i0 + k + half] * wi + im[i0 + k + half] * wr
                re[i0 + k] = u_r + v_r
                im[i0 + k] = u_i + v_i
                re[i0 + k + half] = u_r - v_r
                im[i0 + k + half] = u_i - v_i
                nwr = wr * wlen_r - wi * wlen_i
                wi = wr * wlen_i + wi * wlen_r
                wr = nwr
        length <<= 1
    half = n // 2
    out = [0.0] * half
    scale = 1.0 / n
    for i in range(half):
        out[i] = math.hypot(re[i], im[i]) * scale
    return out


def _band_energies(mags: Sequence[float], bands: int, sr: int = _SR) -> list[float]:
    """Log-ish frequency grouping from FFT bins → band energies 0..1."""
    n = len(mags)
    if n < 2 or bands < 1:
        return [0.0] * max(1, bands)
    # skip DC bin 0; use 1..n-1
    lo_hz, hi_hz = 40.0, min(sr / 2.0 * 0.95, 5000.0)
    edges = [
        lo_hz * ((hi_hz / lo_hz) ** (i / bands))
        for i in range(bands + 1)
    ]
    out = [0.0] * bands
    for b in range(bands):
        i0 = max(1, int(edges[b] / sr * (n * 2)))
        i1 = max(i0 + 1, int(edges[b + 1] / sr * (n * 2)))
        i1 = min(n, i1)
        chunk = mags[i0:i1] or mags[min(i0, n - 1) : min(i0, n - 1) + 1]
        # RMS-ish
        e = math.sqrt(sum(x * x for x in chunk) / max(1, len(chunk)))
        # gentle log compress
        out[b] = math.log1p(e * 80.0) / math.log1p(80.0)
    # normalize to peak
    peak = max(out) if out else 0.0
    if peak > 1e-6:
        out = [min(1.0, v / peak) for v in out]
    return out


def _ffmpeg_slice(path: str, t: float) -> list[float] | None:
    if not path or not Path(path).is_file():
        return None
    # start a little before so we have a full window
    ss = max(0.0, float(t) - _SAMPLE_SECS * 0.5)
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        f"{ss:.3f}",
        "-t",
        f"{_SAMPLE_SECS * 1.5:.3f}",
        "-i",
        path,
        "-ac",
        "1",
        "-ar",
        str(_SR),
        "-f",
        "f32le",
        "-n",  # no overwrite prompts
        "pipe:1",
    ]
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            timeout=0.22,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    raw = p.stdout or b""
    need = _N * 4
    if len(raw) < need // 2:
        return None
    # take last _N samples if we got more
    n_samp = len(raw) // 4
    if n_samp < 32:
        return None
    fmt = f"<{n_samp}f"
    try:
        samples = list(struct.unpack(fmt, raw[: n_samp * 4]))
    except struct.error:
        return None
    if len(samples) > _N:
        samples = samples[-_N:]
    elif len(samples) < _N:
        samples = samples + [0.0] * (_N - len(samples))
    # Hann window
    out = []
    for i, x in enumerate(samples):
        w = 0.5 - 0.5 * math.cos(2.0 * math.pi * i / max(1, _N - 1))
        out.append(x * w)
    return out


def _fallback_bands(bands: int, t: float, *, active: bool, vol: float) -> list[float]:
    """Pretty reactive fake spectrum when we cannot sample audio."""
    if not active:
        # still water — low gentle ripples
        return [
            0.04 + 0.03 * math.sin(t * 0.7 + i * 0.4) ** 2
            for i in range(bands)
        ]
    out = []
    for i in range(bands):
        # multi-harmonic motion, bass heavier
        bass_w = 1.0 - (i / max(1, bands - 1)) * 0.55
        v = 0.0
        v += 0.55 * abs(math.sin(t * (1.3 + i * 0.11) + i))
        v += 0.30 * abs(math.sin(t * (2.7 + i * 0.07) + i * 1.7))
        v += 0.20 * abs(math.sin(t * (5.1 + i * 0.19)))
        # occasional "kick"
        kick = max(0.0, math.sin(t * 2.0)) ** 8
        if i < bands // 4:
            v += 0.45 * kick
        v *= bass_w * (0.45 + 0.55 * vol)
        out.append(max(0.0, min(1.0, v)))
    return out


def _smooth(prev: list[float], target: list[float], attack: float, release: float) -> list[float]:
    if not prev or len(prev) != len(target):
        return list(target)
    out = []
    for a, b in zip(prev, target):
        k = attack if b > a else release
        out.append(a + (b - a) * k)
    return out


def update_levels(
    *,
    bands: int = 16,
    path: str = "",
    pos: float = 0.0,
    playing: bool = False,
    paused: bool = False,
    volume: float = 0.7,
) -> list[float]:
    """Refresh smoothed band levels. Call once per UI frame."""
    global _levels, _last_sample_t, _last_path, _last_pos, _source
    bands = max(8, min(32, int(bands)))
    now = time.monotonic()
    active = bool(playing and not paused)

    target: list[float] | None = None
    # Sample rate independent of UI FPS (ffmpeg is the heavy bit).
    # Env SIREN_WAVES_HZ (default 14) — live FFT; UI can still redraw faster
    # on fallback motion between samples.
    try:
        # Match snappier waves UI (~30fps); sample a bit under that to spare ffmpeg
        hz = float(os.environ.get("SIREN_WAVES_HZ", "18"))
    except ValueError:
        hz = 18.0
    sample_period = 1.0 / max(4.0, min(40.0, hz))
    due = (now - _last_sample_t) >= sample_period
    # Resample if transport moved enough OR enough time passed while playing
    moved = abs(pos - _last_pos) > 0.02 or path != _last_path
    if active and path and due and (moved or path == _last_path):
        samples = _ffmpeg_slice(path, pos)
        _last_sample_t = now
        _last_path = path
        _last_pos = pos
        if samples:
            mags = _fft_mags(samples)
            target = _band_energies(mags, bands)
            _source = "live"
    if target is None:
        target = _fallback_bands(bands, now, active=active, vol=volume)
        if active and _source != "live":
            _source = "fall"
        elif not active:
            _source = "idle"

    # if band count changed, reset smooth state
    if len(_levels) != bands:
        _levels = list(target)
    else:
        # live attacks faster so kicks punch; fallback a bit softer
        atk = 0.55 if _source == "live" else 0.35
        rel = 0.18 if _source == "live" else 0.22
        if not active:
            atk, rel = 0.2, 0.12
        _levels = _smooth(_levels, target, atk, rel)
    return list(_levels)


def source_label() -> str:
    return {
        "live": "live sample",
        "fall": "tide echo",
        "idle": "still water",
    }.get(_source, _source)


def render_eq_rows(
    levels: Sequence[float],
    *,
    height: int = 8,
    col_w: int = 2,
    gap: int = 0,
    body_w: int | None = None,
) -> list[str]:
    """Vertical ASCII bars as equal-width plain lines (no ANSI).

    When body_w is set, band columns are *distributed across the full width*
    (remainder pixels go to the leftmost bands) so the EQ fills the panel
    instead of sitting in a skinny cluster on the left.
    """
    if not levels:
        levels = [0.0]
    height = max(4, min(16, height))
    n = len(levels)
    if body_w is not None and body_w > 0 and n > 0:
        # Fill the whole body: no gaps, variable column widths.
        gap = 0
        base = max(1, body_w // n)
        # if base*n still short of body_w, grow some columns
        widths = [base] * n
        # first pass: if base*n > body_w (too many bands), shrink from the right
        while sum(widths) > body_w and any(w > 1 for w in widths):
            for i in range(n - 1, -1, -1):
                if sum(widths) <= body_w:
                    break
                if widths[i] > 1:
                    widths[i] -= 1
        # second pass: distribute leftover columns left-to-right
        rem = body_w - sum(widths)
        i = 0
        while rem > 0 and n:
            widths[i % n] += 1
            rem -= 1
            i += 1
    else:
        col_w = max(1, min(4, col_w))
        gap = max(0, min(1, gap))
        widths = [col_w] * n

    hs = [int(round(max(0.0, min(1.0, v)) * height)) for v in levels]
    rows: list[str] = []
    for y in range(height, 0, -1):
        parts = []
        for i, h in enumerate(hs):
            w = widths[i]
            cell = ("#" * w) if h >= y else (" " * w)
            parts.append(cell)
            if gap and i < n - 1:
                parts.append(" " * gap)
        line = "".join(parts)
        if body_w is not None:
            if len(line) < body_w:
                line = line + (" " * (body_w - len(line)))
            else:
                line = line[:body_w]
        rows.append(line)
    base_parts = []
    for i in range(n):
        base_parts.append("-" * widths[i])
        if gap and i < n - 1:
            base_parts.append("-" * gap)
    base = "".join(base_parts)
    if body_w is not None:
        base = (base + " " * body_w)[:body_w]
    rows.append(base)
    return rows


def colorize_eq_rows(rows: list[str], levels: Sequence[float]) -> list[str]:
    """Tint '#' cells: lower third rose, mid silver, upper baby-blue.

    Operates per-row by scanning characters — keeps vis width == len(plain).
    """
    if not _color_ok() or not rows:
        return rows
    height = max(1, len(rows) - 1)  # last row is baseline
    out = []
    for yi, row in enumerate(rows):
        if yi == len(rows) - 1:
            out.append(_paint(row, ROSE_DIM))
            continue
        # row from top: yi=0 is peak
        from_bottom = height - yi  # 1..height
        frac = from_bottom / height
        if frac > 0.66:
            code = BLUE
        elif frac > 0.33:
            code = ROSE
        else:
            code = ROSE_DIM
        # paint whole row one color (simpler, width-safe)
        # only color hash cells: rebuild
        buf = []
        for ch in row:
            if ch == "#":
                buf.append(_paint("#", code))
            else:
                buf.append(ch)
        out.append("".join(buf))
    return out


def legend_line(bands: int, body_w: int) -> str:
    left = "bass"
    right = "treble"
    mid = f"{bands} band"
    # plain ASCII
    room = max(8, body_w)
    # left mid right
    if len(left) + len(mid) + len(right) + 4 > room:
        return (left + " -> " + right)[:room].ljust(room)
    pad = room - len(left) - len(mid) - len(right)
    left_pad = pad // 2
    right_pad = pad - left_pad
    return left + (" " * left_pad) + mid + (" " * right_pad) + right


def eq_bar_lines(
    *,
    bands: int = 16,
    height: int = 8,
    body_w: int = 60,
    path: str = "",
    pos: float = 0.0,
    playing: bool = False,
    paused: bool = False,
    volume: float = 0.7,
    include_baseline: bool = False,
) -> list[str]:
    """Plain ASCII EQ rows only (the '#' stack). No legend/meta.

    Baseline (row of '-') is static chrome — omit it for in-place animation
    so the frame around the EQ never rewrites.
    """
    levels = update_levels(
        bands=bands,
        path=path,
        pos=pos,
        playing=playing,
        paused=paused,
        volume=volume,
    )
    rows = render_eq_rows(levels, height=height, body_w=body_w)
    if include_baseline:
        return rows
    # last row is baseline dashes
    return rows[:-1] if len(rows) > 1 else rows


def build_waves_body(
    *,
    bands: int = 16,
    height: int = 8,
    body_w: int = 60,
    path: str = "",
    pos: float = 0.0,
    playing: bool = False,
    paused: bool = False,
    volume: float = 0.7,
    color: bool = True,
) -> list[str]:
    """Full open-waves panel body lines (bars + baseline + legend + meta)."""
    levels = update_levels(
        bands=bands,
        path=path,
        pos=pos,
        playing=playing,
        paused=paused,
        volume=volume,
    )
    rows = render_eq_rows(levels, height=height, body_w=body_w)
    if color:
        rows = colorize_eq_rows(rows, levels)
    meta = f"src {source_label()}  |  w close  |  W toggle 16/32"
    if len(meta) > body_w:
        meta = meta[: body_w]
    leg = legend_line(len(levels), body_w)
    return rows + ["", leg, meta]


def demo() -> None:
    """CLI smoke: print a few frames to stdout."""
    import sys

    sys.path.insert(0, str(Path.home() / "bin"))
    import pixie_termart as art

    tw = art.term_width()
    body_w = max(20, tw - 6)
    for frame in range(5):
        body = build_waves_body(
            bands=16,
            height=8,
            body_w=body_w,
            path="",
            pos=frame * 0.2,
            playing=True,
            paused=False,
            volume=0.8,
        )
        # plain for width check: re-render without relying on box
        print(art.box(body, title="open waves", width=tw))
        print("---")
        time.sleep(0.05)


if __name__ == "__main__":
    demo()
