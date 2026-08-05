"""Tests for the shared TUI layer (fae_termart).

Covers the two contracts every faeOS TUI depends on:
  1. tui_read_key — one keypress → stable key name (arrows, CSI, ctrl-*)
  2. box / paint_frame — aligned frames at any width, styled lines kept,
     no CR/LF surprises in raw mode.

Run:  python3 -m pytest tests/  (or: pytest tests/)
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))

import fae_termart as art  # noqa: E402

# Tests never depend on a real TTY or on color output.
os.environ["NO_COLOR"] = "1"
os.environ["PIXIE_UNICODE"] = "1"


# ── helpers ────────────────────────────────────────────────────────────

def feed(data: bytes) -> int:
    """Pipe with `data` queued; read end usable by tui_read_key."""
    r, w = os.pipe()
    os.write(w, data)
    os.close(w)
    return r


def close(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


# ── tui_read_key: plain keys ───────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    (b"q", "q"),
    (b"Q", "Q"),
    (b"\r", "enter"),
    (b"\n", "enter"),
    (b" ", "space"),
    (b"\t", "tab"),
    (b"\x03", "ctrl-c"),
    (b"\x04", "ctrl-d"),
    (b"\x12", "ctrl-r"),
    (b"\x15", "ctrl-u"),
    (b"\x7f", "backspace"),
    (b"\x08", "backspace"),
])
def test_plain_keys(raw, expected):
    fd = feed(raw)
    try:
        assert art.tui_read_key(fd, timeout=1) == expected
    finally:
        close(fd)


def test_timeout_returns_empty():
    import pty as _pty
    m, s = _pty.openpty()
    try:
        assert art.tui_read_key(s, timeout=0.01) == ""
    finally:
        os.close(m)
        os.close(s)


def test_eof_returns_esc():
    # closed pipe reads as EOF: must return a key, never spin
    fd = feed(b"")
    try:
        assert art.tui_read_key(fd, timeout=1) == "esc"
    finally:
        close(fd)


# ── tui_read_key: CSI sequences ────────────────────────────────────────

@pytest.mark.parametrize("seq,expected", [
    (b"\x1b[A", "up"),
    (b"\x1b[B", "down"),
    (b"\x1b[C", "right"),
    (b"\x1b[D", "left"),
    (b"\x1b[Z", "shift-tab"),
    (b"\x1b[5~", "pgup"),
    (b"\x1b[6~", "pgdn"),
    (b"\x1b[H", "home"),
    (b"\x1b[F", "end"),
    (b"\x1b[1~", "home"),
    (b"\x1b[7~", "home"),
    (b"\x1b[4~", "end"),
    (b"\x1b[8~", "end"),
    (b"\x1b[3~", "delete"),
])
def test_csi_sequences(seq, expected):
    fd = feed(seq)
    try:
        assert art.tui_read_key(fd, timeout=1) == expected
    finally:
        close(fd)


def test_ss3_arrows():
    for seq, expected in [(b"\x1bOA", "up"), (b"\x1bOB", "down"),
                          (b"\x1bOC", "right"), (b"\x1bOD", "left")]:
        fd = feed(seq)
        try:
            assert art.tui_read_key(fd, timeout=1) == expected
        finally:
            close(fd)


def test_unknown_csi_passthrough():
    fd = feed(b"\x1b[99")
    try:
        assert art.tui_read_key(fd, timeout=1) == "csi:99"
    finally:
        close(fd)


def test_lone_escape():
    fd = feed(b"\x1b")
    try:
        assert art.tui_read_key(fd, timeout=1) == "esc"
    finally:
        close(fd)


def test_multibyte_utf8_not_a_key():
    # reader is byte-at-a-time: a lone UTF-8 lead byte is not a key (no hang)
    fd = feed("é".encode()[:1])
    try:
        assert art.tui_read_key(fd, timeout=1) == ""
    finally:
        close(fd)


# ── paint / strip / width math ─────────────────────────────────────────

def test_paint_respects_no_color():
    assert art.paint("x", art.P.PINK) == "x"


def test_paint_with_force_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("FORCE_COLOR", "1")
    out = art.paint("x", art.P.PINK)
    assert out.startswith("\x1b[") and out.endswith(art.P.RESET)
    assert art.strip_ansi(out) == "x"


def test_vis_len_strips_ansi():
    assert art.vis_len("\x1b[38;5;175mhello\x1b[0m") == 5
    assert art.vis_len("") == 0
    assert art.vis_len("a✦b") == 3  # box-drawing dingbats are width 1 here


def test_pad_vis_pads_by_visible_width():
    assert art.pad_vis("ab", 4) == "ab  "
    styled = art.paint("ab", art.P.PINK)
    assert art.vis_len(art.pad_vis(styled, 4)) == 4


def test_wrap_plain():
    assert art.wrap_plain("hello world", 5) == ["hello", "world"]
    assert art.wrap_plain("short", 20) == ["short"]


# ── box(): frame geometry ──────────────────────────────────────────────

def box_lines(width, body, **kw):
    frame = art.box(body, width=width, **kw)
    return frame.splitlines()


def test_box_unicode_borders():
    lines = box_lines(44, ["hi"])
    assert lines[0].startswith("╭")
    assert lines[0].endswith("╮")
    assert lines[-1].startswith("╰")
    assert lines[-1].endswith("╯")
    assert lines[1].startswith("│")
    assert lines[1].endswith("│")


def test_box_ascii_fallback(monkeypatch):
    monkeypatch.delenv("PIXIE_UNICODE")
    lines = box_lines(44, ["hi"])
    assert lines[0].startswith("+-")
    assert lines[1].startswith("|")


def test_box_title_and_marks():
    lines = box_lines(44, ["hi"], title="Den")
    assert " ✦ Den ✦ " in lines[0]


def test_box_constant_width():
    for width in (44, 60, 80):
        lines = box_lines(width, ["a", "bb", "ccc"])
        for ln in lines:
            assert art.vis_len(ln) == width


def test_box_wraps_long_plain_lines():
    body = "word " * 30
    lines = box_lines(44, [body])
    content = [ln for ln in lines if ln.startswith("│") and ln.strip(" │")]
    assert len(content) > 1
    assert all(art.vis_len(ln) <= 44 for ln in lines)


def test_box_keeps_prestyled_lines():
    styled = "\x1b[38;5;175mpink text\x1b[0m"
    lines = box_lines(44, [styled])
    content = [ln for ln in lines if ln.startswith("│")]
    assert any("\x1b[38;5;175m" in ln for ln in content)


def test_box_long_title_truncated():
    title = "A very long title that cannot possibly fit"
    lines = box_lines(44, ["x"], title=title)
    assert art.vis_len(lines[0]) == 44
    # extreme overflow: marks are dropped, title cut to a prefix that fits
    assert title[:10] in lines[0]


def test_footer_keys_shape():
    frame = art.footer_keys([("^s", "start"), ("q", "quit")], width=44)
    lines = frame.splitlines()
    assert "runes" in lines[0]
    assert "^s start" in frame and "q quit" in frame


# ── paint_frame: atomic redraw ─────────────────────────────────────────

def test_paint_frame_clears_then_draws():
    r, w = os.pipe()
    art.paint_frame(w, "line1\nline2")
    os.close(w)
    out = b""
    while True:
        chunk = os.read(r, 4096)
        if not chunk:
            break
        out += chunk
    os.close(r)
    text = out.decode("utf-8")
    assert text.startswith("\033[H\033[2J")
    assert "line1" in text and "line2" in text


def test_paint_frame_crlf_in_raw_mode():
    # Non-tty fd: tcgetattr fails → forces CR-LF so raw-mode frames don't staircase
    r, w = os.pipe()
    art.paint_frame(w, "a\nb")
    os.close(w)
    out = b""
    while True:
        chunk = os.read(r, 4096)
        if not chunk:
            break
        out += chunk
    os.close(r)
    assert b"a\r\nb" in out
