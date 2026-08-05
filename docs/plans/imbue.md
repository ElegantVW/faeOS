# Imbue — clipboard memory

**Role:** Remember what you copy. Browse history, re-paste, filter. The copy-spell for faeOS.

**Status:** new (v1)

## Current
- `imbue` — TUI history (↑↓ · enter re-copy · y print+quit · d delete · / filter)
- `imbue list [N]` — recent clips (stdout)
- `imbue get` — current system clipboard (or last imbue)
- `imbue set <text>` / `imbue set -` — write clipboard + store
- `imbue add <text>` — store only (no system clipboard write)
- `imbue watch` — poll clipboard, append new text
- `imbue clear` — wipe history
- `imbue backend` — which bridge is live

## Clipboard backends (first that works)
1. `wl-copy` / `wl-paste` (Wayland)
2. `xclip`
3. `xsel`
4. Pure **ctypes + libX11** (CLIPBOARD + PRIMARY, no package deps)
5. Internal board only (`~/.local/share/faeos/imbue/current.txt`) if no display

## Storage
`$XDG_DATA_HOME/faeos/imbue/history.jsonl`  
Dedup consecutive identical; max 500 entries; text cap 256 KiB.

## Next
- [ ] Image clips (optional)
- [ ] systemd user unit for `imbue watch`
- [ ] Secret redaction heuristics (optional)
