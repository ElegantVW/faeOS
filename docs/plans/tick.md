# Tick / Termfix — screen management

**Role:** `tick` — periodic prompt redraw (music, status) while idle; `termfix` — TTY line-edit recovery (cooked/raw mishaps, e.g. after TUIs).

**Status:** stable

## Current
- Tick honors `pixie-screen allowed` (never clears under a hold)
- `PIXIE_NO_AUTOSUGGEST=1` + `termfix` for kmscon

## Next
- [ ] Tick cost budget (no measurable prompt lag)
- [ ] termfix: auto-recover after TUI crashes (hook into tui_cleanup failures?)

## Notes
- Tightly coupled with prompt widgets (`starship-*`).
