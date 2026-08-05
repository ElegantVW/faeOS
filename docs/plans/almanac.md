# Almanac — calendar hub

**Role:** Month view + day agenda. The third piece of the calendar system.

**Status:** new (v1)

## Current
- Own events: `$XDG_DATA_HOME/faeos/almanac/events.json`
- **Feeds (read-only):**
  - Quests with `due:YYYY-MM-DD`
  - Hourglass sessions whose `ts` falls on that day
- TUI: month grid (marks days with items), cursor day agenda
- Keys: arrows day · `[` `]` month · `n` event · `Q` launch quests · `H` launch hourglass · `t` today
- CLI: `almanac today` · `almanac day YYYY-MM-DD`

## Architecture
```
  Almanac (hub) ──reads──► Quests todo.txt
                 ──reads──► Hourglass sessions.jsonl
                 ──owns───► events.json

  Quests  ── standalone CLI/TUI ──► same todo.txt
  Hourglass ── standalone CLI/TUI ──► same sessions.jsonl
```
Peers never depend on Almanac.

## Next
- [ ] Week view
- [ ] Reminders / tick integration
