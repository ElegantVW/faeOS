# Vault — disk treasure map

**Role:** Find what's eating the disk. Recursive sizes, dive toward heavy dirs. The scales next to Spellbook's library and The Eye's process gaze.

**Status:** new (v1)

## Current
- `vault [path]` — TUI at path (default `$HOME`); hold name `vault`
- Header: path · this-dir total · disk used/total bar · free
- Table: SIZE · % of parent · name (`/` dirs, `@` links); `~` size if scan timed out
- Keys: ↑↓ dive (enter/l/→) · parent (h/←/backspace) · `s` size↔name · `r` reverse · `R` rescan · **`d` delete (y/n confirm)** · `/` filter · `.` hidden · `q`
- Recursive weigh: no symlink follow; hardlink de-dupe within a tree; unreadable skipped
- Cache: `path → (mtime, entries, total)` so re-entry is instant until dir mtime changes
- Progress while scanning; 180s budget with partial mark
- One-shot: `vault list [N] [path]`
- Layout: head/runes measured first; chests (list) flex; never scrolls header off (same as Eye)

## Not (Spellbook's job)
- Open/edit/rename/delete files, shared `--pick` dialog

## Next
- [x] Delete selected (with confirm) — `d` → y/n; rmtree/unlink; refuse `/` and `$HOME`; rescan after
- [ ] Skip other mount points (`st_dev` change)
- [ ] Parallel or incremental rescan of one child
- [ ] Export report (`vault list > report.txt` already works)

## Notes
- Pure stdlib (`os.scandir` / `lstat` / `statvfs`). No du(1) required.
- Large homes take time on first open; cache + `R` keep it usable.
