# faeOS design language

Pink, pastel, rounded crystal frames — one house look for TUIs and standalones.

## Chrome

```
╭─ ✦ title ✦ ──────────────────────────────╮
│ body                                     │
╰──────────────────────────────────────────╯
```

- **Unicode** when `PIXIE_UNICODE=1` (most interactive apps set this).
- **ASCII** fallback for kmscon: `+-- * title * --+`.
- Palette: `fae_termart.Palette` (256-color pinks) + `config/palette.env` for X/kitty.
- Shared Python layer: `bin/fae_termart.py` — `box`, `panel`, `split_row`, `tui_*`, mouse HitMap.

## Terminal first (product principle)

faeOS should make the **terminal** the superpower: keyboard-first, fast, scriptable.

- Mouse is **optional convenience** on list TUIs (click/select, wheel), not a requirement.
- Teach discovery via `scroll`, human-ish voice via `docs/cli-voice.md`, and always keep machine CLIs.
- A future hybrid terminal/graphical shell may grow out of `fae_termart` / Rift — still with terminal as the hero path. “Ditch the mouse” remains the long-term skill pitch; mouse must never be the only way.

## Mouse (day-to-day)

| Layer | API |
|-------|-----|
| Enable | `tui_begin(fd, name, mouse=True)` — SGR 1006 |
| Read | `tui_read_event()` → `str \| MouseEvent` |
| Regions | `HitMap` + `add_list_rows` + `DoubleClickTracker` |
| Compat | `tui_read_key()` discards mouse |

Always disable mouse in `tui_cleanup`. Shift+drag stays with the terminal for text selection.

**Apps with clickable lists (wave 2):** Siren · Scroll (fae + PATH tabs; Summon = PATH) · Spellbook  
(click select · double-click activate · wheel). Keyboard remains complete.

**Scroll / Summon:** encyclopedia of every app (except Kur) with intro · how+keys · CLI · runes that **run** the app; PATH tab / `summon` for system launcher. Cries/sprites per creature: future Scroll-only flavor.

## Languages

| Tier | When | Examples |
|------|------|----------|
| Rust | privilege, speed, long-running | Bulwark, Seal, Fairy-Lantern, Wisp, Hearth, Rift |
| Python | house TUIs, glue | Siren, Imp, Spellbook, Scroll… |

Stay lean (suite ≪ 100 MB). No big-bang rewrite.

## Related

- CLI human voice (per-app trees): [cli-voice.md](cli-voice.md)
- Error voice (failures, all ages): [error-voice.md](error-voice.md)
- Screen clear policy: [screen-policy.md](screen-policy.md)
- Master plan: [../faeOSplan.md](../faeOSplan.md)
