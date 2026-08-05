# Quests — todo log

**Role:** Personal quest board in todo.txt format. Fully independent.

**Status:** new (v1)

## Current
- File: `$XDG_DATA_HOME/faeos/quests/todo.txt` (override `QUESTS_FILE`)
- Format: `(A) text +project @context due:YYYY-MM-DD` · done `x YYYY-MM-DD …`
- TUI: complete / new / delete / filter / show-done
- CLI: `list` `add` `done` `due`
- **Export for Almanac:** `quests_due_on(date)` · `quests_open()`

## Independence
Almanac may import this module read-only. Quests never imports Almanac.

## Next
- [ ] Recurring quests
- [ ] Projects view (+tag)
