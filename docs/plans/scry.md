# Scry — history (visions)

**Role:** Command + output history, one vision at a time, Shift-Tab launcher. Peer into what was cast.

**Status:** stable

## Current
- `scry` TUI (own tty, alt screen, hold): ↑↓/n/p/j/k browse, / fzf jump list, r re-run spell onto prompt, q/esc leave
- `scry-log` backend (`list -n`, JSON per event); Shift-Tab keybinding in shell
- Runs on shared `tui_*` layer (shift-tab now canonical in `tui_read_key`)

## Next
- [ ] Search filter inside the vision loop (not just fzf jump)
- [ ] Output truncation/summary view for long outputs
- [ ] Export a vision (save to file / send to magpie?)

## Notes
- Data stays local under `~/.cache/pixie/scry/`.
