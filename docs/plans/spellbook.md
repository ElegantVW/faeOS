# Spellbook — file manager

**Role:** Terminal file manager with fae styling; dialogs for create/delete/rename/edit; optional xdg-open.

**Status:** stable

## Current
- `spellbook [dir]` — TUI: j/k/↑↓ move, l/o open, h parent, ? help, s sort, . hidden, n/d/r/e dialogs
- `spellbook --pick --output <file> [dir]` — **shared file picker**: choose a file, write path to `<file>`, exit (other apps call this)
- Sort by name/date/size/type; input() dialogs use `tui_suspend`/`tui_resume`
- Runs on shared `tui_*` layer (alt screen + hold)
- Location bar: breadcrumbs (click a crumb to jump); **Ctrl+L** / **:** to type a path; **y** yank selected / **Y** yank shelf via `imbue`; **P** paste-go from the board; Enter/Esc in the bar

## Next
- [ ] Config persistence (sort, hidden, cwd remember)
- [ ] Preview pane for text files
- [ ] Copy/move between dirs (files, not the location string)
- [ ] File size/date columns + human formats
- [ ] Search within dir (fzf-style)

## Notes
- Do NOT merge with scroll (help) — distinct roles.
