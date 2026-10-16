# Spellbook — file manager

**Role:** Terminal file manager with fae styling; dialogs for create/delete/rename/edit; optional xdg-open. Shared `--pick` for Tome and Fairy Lantern.

**Status:** Rust engine (v0.2). Canonical tree `~/spellbook` (`ElegantVW/spellbook`). Python `bin/spellbook` retired.

## Current

- Engine: ELF `~/.local/lib/faeos/spellbook`, launcher `~/bin/spellbook`. Build: `cd ~/spellbook && ./build.sh install --house`.
- Event-driven ratatui (no 10 Hz full-screen paint, listing cached until the shelf changes). Kind tints, light `▸` focus, click/double-click/wheel.
- `spellbook [dir]` — TUI: j/k/↑↓ move, l/o/enter open, h parent, ? help, s sort, . hidden, n/d/r/e in-TUI prompts
- `spellbook --pick --output <file> [dir]` — shared file picker
- Location bar: breadcrumbs (click a crumb); **Ctrl+L** / **:** to type a path; **y** yank / **Y** yank shelf via `imbue`; **P** paste-go
- Open files with `xdg-open` (spawn, does not block the TUI). `e` suspends into `$EDITOR`.

## Next

- [ ] Config persistence (sort, hidden, cwd remember)
- [ ] Preview pane for text files
- [ ] Copy/move between dirs (files, not the location string)
- [ ] Search within dir (fzf-style)

## Notes

- Do NOT merge with scroll (help) — distinct roles.
- Do NOT absorb Imbue.
