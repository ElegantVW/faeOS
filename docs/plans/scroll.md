# Scroll — Grove's living guide

Canonical repo: `ElegantVW/scroll`. faeOS keeps only a thin launcher.

**Role:** Grove's first guide: one **page per app**; Tab turns lessons; last
leaf is PATH (print to prompt).
**Status:** 35 static pages + egg leaf + PATH leaf = 37 leaves (switcher + tv added 2026-09-28).

## Navigation
- **Tab / Shift-Tab** — next / previous page (`cycle_next` /
  `cycle_previous` in Grove's canonical keyboard catalog)
- **↑ / ↓** — scroll lesson text; on PATH or search, select a result
- **PageUp / PageDown** — move by one screen within lesson text or result lists
- **Mouse wheel** — scroll lesson text or move the PATH selection
- **1–9** — cast footer runes (**run** the spell)
- **Ctrl+F** — search lesson names, commands, topics, and page text; Enter opens
- **Launch splash** — sigil, scrambling title, rounded frame, and welcome cue;
  any key or mouse skips it; `q` quits
- **Vertical page turn** — Tab brings the next lesson from below; Shift+Tab
  brings the previous lesson from above
- **Reduced motion** — `SCROLL_REDUCED_MOTION=1` skips the splash and disables
  page-turn motion
- **PATH leaf** — filter · Enter → print name for shell `print -z`
- Layout: rounded, color-layered panels with a small outer margin

## Curriculum
Python fallback order is in `CURRICULUM` in `scroll_pages.py`; Rust order and
app/command copy lives in `data/pages.json`. Both end with **switcher**, **tv**,
then the **Sealed Leaf** (or **Kur** if hatched), then **PATH**. Keep both
copies aligned while the Python rollback remains supported. Appending new pages
at the end keeps the lesson order stable. The Rust app is the polished
Grove-first tutorial; the Python script remains a minimal rollback and does
not promise visual or keybinding parity.

## Rust app and launcher
- Build with `cargo build --release`; launch `target/release/scroll-rs`.
- `Ctrl-F` opens the searchable app index and quick-jump.
- The Rust app is self-contained: it reads faeOS egg state directly and
  optionally uses its own mpv ambience socket. It does not import Pixie
  internals or edit faeOS shared libraries.
- faeOS `bin/scroll` prefers Rust from the installed faeOS locations or
  `~/scroll/target/release/scroll-rs`, then falls back to Python. `bin/summon`
  remains the Python argv/env adapter that selects the PATH leaf.
- For shell capture, Rust draws through `/dev/tty` while stdout contains only
  the selected command; a PTY test verifies this contract. This lets the
  `pixie.zsh` `summon` and `scroll --path` wrappers continue to use `print -z`.
- Roll back to Python for a command with
  `SCROLL_BIN="$HOME/scroll/scroll" summon` (or `scroll --path`).
- Rust preserves the shared `~/.cache/pixie/summon.list` format and six-hour
  TTL; cache writes are atomic and refresh errors are reported.
- Rust page text is maintained in `data/pages.json` against current faeOS
  app/CLI documentation. Keep `scroll_pages.py` aligned until the Python
  rollback is retired.
- The Rust display uses one semantic Scroll palette and rounded frames.
  `SCROLL_UNICODE=ascii` selects ASCII panel borders and `NO_COLOR` disables
  terminal colors.
- Developer and AI-agent guidance lives in `docs/development.md` and root
  `AGENTS.md`; Codex harvests both from this canonical repository.

## Sealed Leaf / egg
- Story: an **egg in the Menagerie** to hatch; points at **`murmur`** (babbling glass).
- No hand-holding, no true name, no solve path in docs.
- Leaf turns only after the player completes hatch tasks (not from murmur alone).

## Python fallback runtime deps (house libs, stay in faeOS)
`fae_termart` (frames), `fae_egg` (hatch state), `fae_ambience` (book music).
`scroll` puts its own dir first on `sys.path`, then `~/bin`.
