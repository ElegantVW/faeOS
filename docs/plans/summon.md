# Summon — PATH tab of Scroll

**Role:** Short name for the **PATH launcher** tab of the unified `scroll` picker.  
**Status:** stable (merged into scroll 2026-08-16)

## Current
- `summon` → `exec scroll` with argv0 `summon` → opens **PATH** tab
- Cache: `~/.cache/pixie/summon.list` (6h TTL); `summon --refresh`
- `summon -x <query> [args…]` — exec first PATH match (no TUI)
- `summon --list` — dump PATH names
- Shell: `pixie.zsh` wraps bare summon with `print -z`

## Fae spells
Not here — use `scroll` and switch tabs (Siren · Pixie · Ether · …), or `scroll list`.

## Notes
- Implementation lives in `bin/scroll`; `bin/summon` is a thin exec wrapper.
- Mouse / filter / cache behaviour shared with the PATH tab of scroll.
- `bin/scroll` prefers `~/.local/lib/faeos/scroll-rs`,
  `/usr/local/lib/faeos/scroll-rs`, then `~/scroll/target/release/scroll-rs`;
  the Python implementation remains the fallback.
- Rust writes its picker to the controlling TTY when stdout is captured by
  the `pixie.zsh` `print -z` widget, leaving stdout for the selected command.
- Roll back one invocation with `SCROLL_BIN="$HOME/scroll/scroll" summon`
  or `SCROLL_BIN="$HOME/scroll/scroll" scroll --path`.
