#!/usr/bin/env python3
"""Shared terminal art for the Pixie stack — pink, whimsical, consistent boxes.

Used by scry, ask/pixie, cmds, duck, etc. Import from ~/bin:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.home() / "bin"))
    import fae_termart as art
"""
from __future__ import annotations

import atexit
import fcntl
import os
import re
import select
import shutil
import struct
import subprocess
import sys
import termios
import unicodedata
from typing import Iterable

ANSI_RE = re.compile(r"\033\[[0-9;]*[mK]")

# Optional controlling TTY fd for size + live redraw (set by scry/siren TUIs).
_size_fd: int | None = None
# Force color even when stdout is not a tty (drawing goes to /dev/tty).
_force_color: bool = False


class Palette:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    ITALIC = "\033[3m"
    DIM = "\033[2m"
    PINK = "\033[38;5;175m"
    DARK = "\033[38;5;168m"
    PINK_DIM = "\033[38;5;132m"
    BLUSH = "\033[38;5;218m"
    SILVER = "\033[38;5;252m"
    MUTED = "\033[38;5;245m"
    OK = "\033[38;5;78m"
    WARN = "\033[38;5;214m"
    ERR = "\033[38;5;197m"


P = Palette

# Shared wait messages for when Pixie is processing
PIXIE_WAIT = (
    "Pixie is poking around…",
    "Contacting the fey world, please wait…",
    "Pixie is dusting off her spellbook…",
    "Pixie is chasing a thought through the wires…",
    "Pixie is listening to the machine spirits…",
    "Pixie is braiding a reply out of moonlight…",
    "Hold still — Pixie is concentrating…",
    "Pixie wandered into /tmp and got distracted…",
    "Pixie is counting sparkles in the cache…",
    "Pixie is negotiating with the kernel gnomes…",
    "Pixie is untangling a knot of pointers…",
    "Pixie is whispering to the inode fairies…",
    "Pixie is polishing her answer with starlight…",
    "Pixie is peeking under the root of the problem…",
    "Pixie is sipping tea from a thimble of RAM…",
    "Pixie is mapping the lay of the home directory…",
    "Pixie is asking the pipes which way is north…",
    "Pixie is humming a little compile song…",
    "Pixie is sorting wishes by priority…",
    "Pixie is chasing a runaway null…",
    "Pixie is rolling up her sleeves (figuratively)…",
    "Pixie is consulting the ancient man pages…",
    "Pixie is balancing on a stack frame…",
    "Pixie is bribing the scheduler with cookies…",
    "Pixie is drawing a tiny map of your request…",
    "Pixie is waiting for the moon to align with /dev…",
    "Pixie is shaking the magic 8-bit ball…",
    "Pixie is retying her boots for another try…",
    "Pixie is listening for the click of a good idea…",
    "Pixie is sweeping cobwebs out of the heap…",
)

# Shared paths
from pathlib import Path
BIN = Path.home() / "bin"
PIXIE_SCREEN = BIN / "pixie-screen"


def bind_tty(fd: int | None, *, color: bool = True) -> None:
    """Bind ioctl size + color to a controlling TTY for live TUIs."""
    global _size_fd, _force_color
    _size_fd = fd
    _force_color = bool(color and fd is not None)


def color_ok() -> bool:
    if os.environ.get("NO_COLOR", "").strip():
        return False
    if _force_color:
        return True
    if os.environ.get("FORCE_COLOR", "").strip() or os.environ.get("CLICOLOR_FORCE", "").strip():
        return True
    try:
        return os.isatty(1) or os.isatty(2)
    except Exception:
        return False


def paint(text: str, *codes: str) -> str:
    if not color_ok() or not codes:
        return text
    return "".join(codes) + text + P.RESET


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def _char_width(ch: str) -> int:
    """Column width for monospace terminals (kmscon/xterm).

    Box-drawing and dingbats (✦ ♪) are width 1 here — treating them as 2
    misaligns right borders on most European fonts.
    """
    if not ch:
        return 0
    o = ord(ch)
    if o < 32 or 0x7F <= o < 0xA0:
        return 0
    if unicodedata.combining(ch):
        return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("F", "W"):
        return 2
    # Emoji & symbols that are double-width on most terminals
    if 0x1F300 <= o <= 0x1FAFF:
        return 2
    return 1


def vis_len(s: str) -> int:
    return sum(_char_width(c) for c in strip_ansi(s))


def winsize(fd: int | None = None, default: tuple[int, int] = (80, 24)) -> tuple[int, int]:
    """Return (cols, rows) via TIOCGWINSZ on fd, else shutil / defaults."""
    for candidate in (fd, _size_fd, 1, 0):
        if candidate is None:
            continue
        try:
            raw = fcntl.ioctl(candidate, termios.TIOCGWINSZ, b"\x00" * 8)
            rows, cols, _, _ = struct.unpack("HHHH", raw)
            if cols > 0 and rows > 0:
                return int(cols), int(rows)
        except Exception:
            continue
    try:
        sz = shutil.get_terminal_size(default)
        return int(sz.columns), int(sz.lines)
    except Exception:
        return default


def term_width(default: int = 72, *, cap: int = 96, floor: int = 44, margin: int = 1) -> int:
    """Usable box width. margin keeps the last column free so print+newline
    does not auto-wrap (kmscon/xterm xenl) and shatter right borders on n/p."""
    cols, _ = winsize(_size_fd)
    if cols <= 0:
        cols = default
    usable = max(1, cols - max(0, margin))
    return max(floor, min(usable, cap))


def term_height(default: int = 24) -> int:
    _, rows = winsize(_size_fd)
    if rows <= 0:
        rows = default
    return max(12, rows)


def tty_write(fd: int, text: str) -> None:
    """Write UTF-8 text to a TTY fd (no Python stream buffering surprises).

    If OPOST is off (classic tty.setraw), bare \\n does not return the cursor
    to column 0 — frames staircase. Force CR-LF only in that case. When OPOST
    is on (set_ui_mode / cbreak), leave \\n alone so the driver can map it.
    """
    if text and "\n" in text:
        need_cr = True
        try:
            oflag = termios.tcgetattr(fd)[1]
            # OPOST on → kernel may already expand \\n to CR-LF (ONLCR)
            need_cr = not bool(oflag & termios.OPOST)
        except (termios.error, OSError):
            need_cr = True
        if need_cr:
            text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    data = text.encode("utf-8", errors="replace")
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        if n <= 0:
            break
        view = view[n:]


def set_ui_mode(fd: int) -> list:
    """Char-at-a-time input WITHOUT killing output post-processing.

    Prefer this over tty.setraw(): setraw clears OPOST so \\n stops doing
    carriage-return and every redraw after the first looks staircase-broken.
    Returns the previous termios attrs (pass to termios.tcsetattr to restore).
    """
    old = termios.tcgetattr(fd)
    # cbreak: no canonical, no echo; OPOST left alone when possible
    try:
        import tty as _tty

        _tty.setcbreak(fd)
    except Exception:
        # manual fallback: like cbreak but keep ONLCR if present
        new = termios.tcgetattr(fd)
        # iflag
        new[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK
                    | termios.ISTRIP | termios.INLCR | termios.IGNCR
                    | termios.ICRNL | termios.IXON)
        # oflag — keep OPOST|ONLCR so newlines still return to col 0
        new[1] |= termios.OPOST
        if hasattr(termios, "ONLCR"):
            new[1] |= termios.ONLCR
        # cflag
        new[2] &= ~termios.CSIZE
        new[2] |= termios.CS8
        # lflag
        new[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON
                    | termios.ISIG | termios.IEXTEN)
        new[6][termios.VMIN] = 1
        new[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSADRAIN, new)
    # After cbreak, explicitly re-assert OPOST|ONLCR (some platforms clear them)
    try:
        cur = termios.tcgetattr(fd)
        cur[1] |= termios.OPOST
        if hasattr(termios, "ONLCR"):
            cur[1] |= termios.ONLCR
        termios.tcsetattr(fd, termios.TCSADRAIN, cur)
    except (termios.error, OSError):
        pass
    return old


def clear_screen(fd: int | None = None) -> str:
    """Home + erase display. Returns CSI string if no fd."""
    # Avoid \033[3J — not all consoles implement scrollback erase cleanly.
    seq = "\033[H\033[2J"
    if fd is not None:
        # clear seq has no newlines; write raw bytes without CR munging
        data = seq.encode("ascii")
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                break
            view = view[n:]
        return ""
    return seq


def paint_frame(fd: int, body: str, *, disable_wrap: bool = True) -> None:
    """Atomic full-frame redraw on controlling TTY.

    Cursor home + erase, then body with CR-LF line ends (raw-mode safe).
    """
    # CSI-only prefix (no newlines) written raw so we do not inject CRs mid-escape
    prefix = "\033[H\033[2J"
    if disable_wrap:
        prefix += "\033[?7l"  # DECAWM off — prevent accidental wrap shredding borders
    data = prefix.encode("ascii")
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        if n <= 0:
            break
        view = view[n:]
    # body via tty_write → CR-LF
    if not body.endswith("\n"):
        body = body + "\n"
    body = body + "\033[0m"
    if disable_wrap:
        body = body + "\033[?7h"
    tty_write(fd, body)


def pad_vis(s: str, width: int) -> str:
    n = vis_len(s)
    if n == width:
        return s
    if n < width:
        return s + (" " * (width - n))
    # truncate by visible width — ASCII ellipsis only
    plain = strip_ansi(s)
    out = []
    w = 0
    # reserve 3 cols for "..."
    limit = max(1, width - 3)
    for ch in plain:
        cw = _char_width(ch)
        if w + cw > limit:
            break
        out.append(ch)
        w += cw
    cut = "".join(out) + "..."
    return cut + (" " * max(0, width - vis_len(cut)))


def wrap_plain(text: str, width: int) -> list[str]:
    """Word-wrap a plain (no ANSI) string; preserves empty lines."""
    if width < 8:
        width = 8
    lines: list[str] = []
    for raw in (text.splitlines() or [""]):
        if not raw.strip():
            lines.append("")
            continue
        indent_m = re.match(r"^(\s*)", raw)
        indent = indent_m.group(1) if indent_m else ""
        content = raw[len(indent) :]
        max_c = max(8, width - len(indent))
        if vis_len(raw) <= width:
            lines.append(raw)
            continue
        words = content.split(" ")
        cur = ""
        for word in words:
            trial = (cur + " " + word).strip() if cur else word
            if vis_len(trial) <= max_c:
                cur = trial
            else:
                if cur:
                    lines.append(indent + cur)
                # hard-break overlong tokens
                while vis_len(word) > max_c:
                    chunk = []
                    w = 0
                    for ch in word:
                        cw = _char_width(ch)
                        if w + cw > max_c:
                            break
                        chunk.append(ch)
                        w += cw
                    lines.append(indent + "".join(chunk))
                    word = word[len("".join(chunk)) :]
                cur = word
        if cur:
            lines.append(indent + cur)
    return lines or [""]


def _ascii_box_enabled() -> bool:
    """Default ASCII frames (kmscon-safe). Set PIXIE_UNICODE=1 for rounded art."""
    v = os.environ.get("PIXIE_UNICODE", "").strip().lower()
    if v in ("1", "on", "true", "yes", "unicode"):
        return False
    return True


def box(
    body: str | Iterable[str],
    *,
    title: str = "",
    subtitle: str = "",
    accent: str | None = None,
    width: int | None = None,
    body_style: tuple[str, ...] = (),
) -> str:
    """Frame for panels. Default is pure ASCII (kmscon-safe):

        +-- * Title --------------------+
        | body line                     |
        +-------------------------------+

    Set PIXIE_UNICODE=1 for rounded Unicode borders.
    """
    acc = accent if accent is not None else P.PINK_DIM
    w = width or term_width()
    outer = max(36, min(w, 96))
    inner = outer - 2  # between left and right border chars
    body_w = inner - 2  # between | sp ... sp |

    ascii_mode = _ascii_box_enabled()
    if ascii_mode:
        tl, tr, bl, br, hz, vt = "+", "+", "+", "+", "-", "|"
        mark = "*"
        ell = "..."
        soft = "-"
    else:
        tl, tr, bl, br, hz, vt = "╭", "╮", "╰", "╯", "─", "│"
        mark = "✦"
        ell = "…"
        soft = "·"

    lines_in: list[str]
    if isinstance(body, str):
        lines_in = []
        for para in body.splitlines() or [""]:
            lines_in.extend(wrap_plain(strip_ansi(para), body_w))
    else:
        lines_in = []
        for para in body:
            for ln in str(para).splitlines() or [""]:
                if ln and strip_ansi(ln) != ln:
                    # pre-styled line: keep ANSI (caller already wrapped it);
                    # too wide → fall back to plain so it gets re-wrapped
                    if vis_len(strip_ansi(ln)) > body_w:
                        ln = strip_ansi(ln)
                    lines_in.append(ln)
                else:
                    lines_in.extend(wrap_plain(ln, body_w))

    # Title bar:  +-- * Title * -----+   (tl + hz + label + fill + tr)
    # Visible: 1 + 1 + len(label) + fill + 1  == outer  => fill = outer - 3 - len(label)
    # With outer = inner + 2: fill = inner - 1 - len(label)
    if title:
        tplain = strip_ansi(title)
        label = f" {mark} {tplain} {mark} "
        if vis_len(label) > inner - 2:
            # keep mark + truncated title
            keep = max(1, inner - 8)
            label = f" {mark} {tplain[:keep]}{ell} {mark} "
            if vis_len(label) > inner - 2:
                label = f" {tplain[: max(1, inner - 4)]} "
        fill = max(0, inner - vis_len(label) - 1)
        top = (
            paint(tl + hz, acc)
            + paint(label, P.BOLD, P.PINK)
            + paint(hz * fill + tr, acc)
        )
    else:
        top = paint(tl + hz * inner + tr, acc)

    out = [top]

    if subtitle:
        for ln in wrap_plain(strip_ansi(subtitle), body_w):
            out.append(
                paint(vt, acc)
                + " "
                + paint(pad_vis(ln, body_w), P.ITALIC, P.DARK)
                + " "
                + paint(vt, acc)
            )
        out.append(
            paint(vt, acc)
            + paint(" " + soft * body_w + " ", acc)
            + paint(vt, acc)
        )

    styles = body_style or (P.SILVER,)
    for ln in lines_in:
        if strip_ansi(ln) != ln:
            # pre-styled line — keep its colors, pad with spaces
            out.append(paint(vt, acc) + " " + ln + " " * max(0, body_w - vis_len(strip_ansi(ln))) + " " + paint(vt, acc))
            continue
        plain = pad_vis(strip_ansi(ln), body_w)
        if plain.strip():
            painted = paint(plain, *styles)
        else:
            painted = " " * body_w
        out.append(paint(vt, acc) + " " + painted + " " + paint(vt, acc))

    out.append(paint(bl + hz * inner + br, acc))
    return "\n".join(out)


def rule(width: int | None = None, *, char: str | None = None) -> str:
    w = width or term_width()
    ch = char if char is not None else ("-" if _ascii_box_enabled() else "─")
    return paint(ch * max(8, w), P.PINK_DIM)


def banner(title: str, tagline: str = "", *, width: int | None = None) -> str:
    """Compact title banner (header strip)."""
    return box("", title=title, subtitle=tagline, width=width, body_style=(P.MUTED,))


def panel_lines(
    rows: list[str],
    *,
    title: str = "",
    accent: str | None = None,
    width: int | None = None,
) -> str:
    return box(rows, title=title, accent=accent, width=width)


def footer_keys(pairs: list[tuple[str, str]], *, width: int | None = None) -> str:
    """Key legend in a slim box:  up/dn next  ·  q leave"""
    bits = []
    for key, label in pairs:
        bits.append(f"{key} {label}")
    line = "  |  ".join(bits)
    return box(line, title="runes", width=width, body_style=(P.MUTED,))


# ---------------------------------------------------------------------------
# shared TUI session layer — one implementation for every pixie TUI
# (siren, scroll, scry, goblin, spellbook, ether): open_tty / screen hold /
# alt screen / cbreak / raw keys / teardown. Kept here so a single fix
# lands everywhere instead of six copies.
# ---------------------------------------------------------------------------

ENTER_ALT = "\033[?1049h\033[?25l"
LEAVE_ALT = "\033[?25h\033[?7h\033[?1049l"
_TUI_HYGIENE = "\033[0m\033[?25h\033[?7h\033[?2004l"

_tui_fd: int | None = None
_tui_old = None
_tui_alt = False
_tui_hold_name: str | None = None


def tui_open_tty() -> int | None:
    """Controlling TTY (or stdin if it is one) for painting + keys."""
    # Try /dev/tty first (standard controlling terminal)
    try:
        return os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        pass
    # Try stdin/stdout/stderr if they are TTYs
    for fd in (0, 1, 2):
        try:
            if os.isatty(fd):
                return os.dup(fd)
        except Exception:
            pass
    # Try to get controlling terminal via os.ctermid() or os.ttyname
    try:
        cterm = os.ctermid()
        if cterm:
            return os.open(cterm, os.O_RDWR | os.O_NOCTTY)
    except Exception:
        pass
    try:
        for fd in (0, 1, 2):
            name = os.ttyname(fd)
            if name:
                return os.open(name, os.O_RDWR | os.O_NOCTTY)
    except Exception:
        pass
    return None


def tui_screen_hold(on: bool, name: str = "pixie") -> None:
    """pixie-screen hold/release so idle-clearing never eats the UI."""
    global _tui_hold_name
    if not PIXIE_SCREEN.is_file():
        return
    try:
        if on:
            subprocess.run([str(PIXIE_SCREEN), "hold", name], check=False, capture_output=True)
            _tui_hold_name = name
        else:
            if _tui_hold_name:
                subprocess.run([str(PIXIE_SCREEN), "release", _tui_hold_name], check=False, capture_output=True)
                _tui_hold_name = None
            subprocess.run([str(PIXIE_SCREEN), "hold", "grace", "20"], check=False, capture_output=True)
    except OSError:
        pass


def tui_cleanup() -> None:
    """Restore termios, leave alt screen, release hold, close the tty fd."""
    global _tui_fd, _tui_old, _tui_alt
    if _tui_old is not None and _tui_fd is not None:
        try:
            termios.tcsetattr(_tui_fd, termios.TCSADRAIN, _tui_old)
        except (termios.error, OSError):
            pass
    if _tui_fd is not None:
        try:
            tty_write(_tui_fd, (LEAVE_ALT if _tui_alt else "") + _TUI_HYGIENE)
        except OSError:
            pass
    _tui_alt = False
    bind_tty(None)
    tui_screen_hold(False)
    if _tui_fd is not None and _tui_fd not in (0, 1, 2):
        try:
            os.close(_tui_fd)
        except OSError:
            pass
    _tui_fd = None
    _tui_old = None


def tui_begin(fd: int, hold_name: str = "pixie") -> None:
    """Start a TUI session: screen hold, alt screen, cbreak, atexit teardown."""
    global _tui_fd, _tui_old, _tui_alt
    _tui_fd = fd
    try:
        _tui_old = termios.tcgetattr(fd)
    except termios.error:
        _tui_old = None
    tui_screen_hold(True, hold_name)
    atexit.register(tui_cleanup)
    bind_tty(fd, color=True)
    try:
        tty_write(fd, ENTER_ALT)
        _tui_alt = True
    except OSError:
        pass
    set_ui_mode(fd)


def tui_read_key(fd: int, timeout: float | None = None) -> str:
    """One keypress: CSI arrows → 'up'/'down'/'left'/'right', CSI Z →
    'shift-tab', 5~/6~ → 'pgup'/'pgdn', H/1~/7~ → 'home', F/4~/8~ → 'end',
    3~ → 'delete', Enter → 'enter', space → 'space', tab → 'tab',
    Ctrl-C → 'ctrl-c', Ctrl-U → 'clear', DEL/BS → 'backspace',
    lone Esc → 'esc', everything else as a single decoded char.
    Returns '' on timeout."""
    if timeout is not None:
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            return ""
    ch = os.read(fd, 1)
    if not ch:
        return "esc"
    if ch == b"\x1b":
        r, _, _ = select.select([fd], [], [], 0.05)
        if not r:
            return "esc"
        n1 = os.read(fd, 1)
        if n1 == b"[":
            seq = b""
            while True:
                r, _, _ = select.select([fd], [], [], 0.05)
                if not r:
                    break
                b = os.read(fd, 1)
                seq += b
                if b and b[0] >= 0x40:
                    break
            s = seq.decode("latin-1", errors="replace")
            if s.startswith("A"):
                return "up"
            if s.startswith("B"):
                return "down"
            if s.startswith("C"):
                return "right"
            if s.startswith("D"):
                return "left"
            if s.startswith("Z"):
                return "shift-tab"
            if s.startswith("5~"):
                return "pgup"
            if s.startswith("6~"):
                return "pgdn"
            if s.startswith(("H", "1~", "7~")):
                return "home"
            if s.startswith(("F", "4~", "8~")):
                return "end"
            if s.startswith("3~") or s.startswith("3"):
                return "delete"
            return f"csi:{s}"
        if n1 == b"O":
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                o = os.read(fd, 1)
                return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(
                    o.decode("latin-1", errors="replace"), "esc"
                )
            return "esc"
        return "esc"
    if ch in (b"\r", b"\n"):
        return "enter"
    if ch == b" ":
        return "space"
    if ch == b"\t":
        return "tab"
    if ch == b"\x03":
        return "ctrl-c"
    if ch in (b"\x04",):
        return "ctrl-d"
    if ch in (b"\x7f", b"\x08"):
        return "backspace"
    if ch in (b"\x15",):  # Ctrl-U
        return "ctrl-u"
    if ch == b"\x12":  # Ctrl-R
        return "ctrl-r"
    try:
        return ch.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def tui_suspend() -> None:
    """Restore cooked terminal mid-TUI (for input() prompts)."""
    if _tui_old is not None and _tui_fd is not None:
        try:
            termios.tcsetattr(_tui_fd, termios.TCSADRAIN, _tui_old)
        except (termios.error, OSError):
            pass


def tui_resume() -> None:
    """Re-enter cbreak after tui_suspend()."""
    if _tui_fd is not None:
        try:
            set_ui_mode(_tui_fd)
        except (termios.error, OSError):
            pass
