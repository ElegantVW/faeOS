# Grimoire — notes

**Role:** Markdown note pages. Quick capture and browse — not a full wiki.

**Status:** new (v1)

## Current
- Storage: `~/notes` (override `GRIMOIRE_DIR`), files `.md` / `.txt` / `.markdown`
- `grimoire` — TUI: list by mtime, title from first `#` heading, preview line
- Keys: enter/e edit · v view · n new · d burn (y/n) · / filter · r refresh · q
- Edit: `$VISUAL` / `$EDITOR` / nano / vim; leave alt-screen then return
- CLI: `list [q]` · `new [title]` · `edit <name>` · `show <name>`
- Height-budgeted layout (Eye/Vault lessons)

## Next
- [ ] Tags (`#tag` harvest + filter by tag)
- [ ] Daily page shortcut (`grimoire today`)
- [ ] Open in Tome when available for fancy markdown

## Notes
- Distinct from Tome (reader) and Spellbook (all files). Grimoire is the note *collection*.
