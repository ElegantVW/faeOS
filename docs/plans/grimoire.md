# Grimoire — notes

**Role:** Markdown note pages. Quick capture and browse — not a full wiki.

**Status:** new (v1) — in-app framed editor

## Current
- Storage: `~/notes` (override `GRIMOIRE_DIR`), files `.md` / `.txt` / `.markdown`
- Chrome: `╭─ ✦ Grimoire ✦ <menu> ✦ <file> ✦ ─╮` + `╭─ ✦ Runes ✦ ─╮` (dynamic width)
- **pages** list · **edit** in-app ink editor · **read** viewer
- Editor: arrows / type / enter / backspace · `^s` save · esc leave (s/d if dirty) · `^a`/`^e` line
- Escape hatch: `E` on pages → external `$EDITOR` on cooked tty
- CLI: `list` `new` `edit` `show` (edit/new open in-app editor when tty present)

## Next
- [ ] Tags (`#tag` harvest + filter by tag)
- [ ] Daily page shortcut (`grimoire today`)
- [ ] Undo stack

## Notes
- Distinct from Tome (reader) and Spellbook (all files). Grimoire is the note *collection*.
- IXON is cleared in TUI mode so `^s` reaches the app (not XOFF).
