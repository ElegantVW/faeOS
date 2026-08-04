# Tome — Document Reader (Scriptorium)

**Role:** Read documents in the terminal — the reader of the future **Scriptorium** office pack (Tome · Grimoire notes · Quill editor · Almanac calendar · Ledger spreadsheets).

**Status:** v0.1 — new (2026-08-03)

## Current
- `tome <file>` — read a document; `tome` (or a dir) — browse readable files, enter opens
- Markdown rendering: headings (pink by level), bullets/numbered, blockquotes, code fences, tables (aligned, header rule), inline `code`, **bold**, *italic*, `[links]` shown with →url, horizontal rules
- Plain-text fallback for `.txt` / `.log`
- Keys: `j/k` scroll, `space`/`pageup`/`ctrl-u` page, `g/G` top/bottom, `/` search (case-insensitive, highlight, `n/N` next/prev, live match count), `Tab` contents (heading jump), `o` open another file (picker starts in current file's dir), `b` back to previous file, `q/esc` quit, resize-aware
- Reads via the shared TUI layer (`fae_termart`) + the shared title style (`✦ Tome — <file> ✦`)

## Design (growth)
- **Format registry** (`FORMATS` in bin/tome): `suffix → (label, renderer)`; renderers emit `(plain, runs)` lines where runs are `[(text, style-codes)]` — pdf/epub/html just need a renderer entry
- Wrapping is run-based (width-aware, CJK-safe via `_char_width`); search operates on the plain row text, highlight re-styles runs
- New `box()` capability used here (and now available to all apps): **pre-styled body lines keep their ANSI colors** instead of being flattened to `body_style`

## Next
- [ ] PDF / epub renderers (pdftotext / epub → text pipeline)
- [ ] Follow links inside docs (open with zen/magpie, or another tome)
- [ ] Recent documents list (`tome --recent`)
- [ ] Code-fence language tinting; task-list checkboxes (markdown extras)
- [ ] Split view: two documents side by side
- [ ] Spellbook picker: `o` key opens shared file picker (spellbook --pick) for seamless file switching

## Notes
- Scriptorium pack umbrella: reader (Tome) → notes (Grimoire) → editor (Quill) → calendar (Almanac) → sheets (Ledger) — Tome's renderer registry is the shared foundation for the pack.
