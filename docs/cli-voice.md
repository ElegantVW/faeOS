# faeOS CLI voice — human grammar tracker

> **Working document.** Human-facing command wording is decided **app by app**.
> There is no single universal transform. Machine CLIs stay stable for scripts.
> Failures / stderr voice: [error-voice.md](error-voice.md).

## Philosophy

Creatures differ in **agency**:

| Kind | Mental model | Voice |
|------|----------------|-------|
| **Aware** (Siren, Pixie, maybe Goblin) | You *ask* them to act | Tool-first or “ask the creature” feels right: `siren play lofi`, `pixie "…"`, later `ask pixie …` |
| **Instrument / messenger** (planned Raven, some utilities) | You *send* or *use* them | Verb carries the human: `send raven with "hello"` — not `raven send` |
| **Layered wards** (Bulwark) | Named powers | Noun-led or ritual: `activate bulwark`, `Ward report`, `Aegis protect` |
| **Craft** (Imp, Alchemy) | Spell + medium | `imp paint "a dragon"`, `brew alchemy firefox` |

When we add a human layer (entrypoint name TBD: `fae` / shell verbs), each app gets a **branch** below: human forms → machine argv. Unmapped = not implemented yet.

Machine form is always valid. Human form is optional sugar.

---

## Syntax trees (by creature)

### Siren (aware — music)

```
siren
├── (bare)                    → TUI
├── play <query|path|playlist>
├── pause | toggle | stop | next | prev
├── now | status | random
├── queue …
├── playlist …
├── config get|set …
└── trove …

human (sketches)
├── siren play lofi           → same (already natural: ask Siren to play)
├── play siren with lofi      → optional alias only if we want verb-first house-wide
└── pause siren / stop siren  → siren pause / siren stop
```

**Decision (draft):** prefer **machine = human** for Siren (`siren play …`). Do not force `play siren with` as primary.

### Imp (craft — art)

```
imp
├── (bare)                 → TUI
├── "<wish>"               → one-shot conjure
├── --style … --demo --gallery --animate …
└── …

human (agreed direction)
└── imp paint "a dragon"   → imp "a dragon"   [primary human form]
```

### Bulwark (wards — protection)

```
bulwark
├── (bare) / tui / tour
├── status | ports | sentinel | ward
├── aegis show|status|apply|confirm|undo
├── purity baseline|check
└── install | uninstall

human (agreed)
├── (bare) bulwark         → TUI look (primary all-ages ritual)
├── look bulwark           → bulwark status
├── activate bulwark       → ensure dirs + status; invite Raise Aegis if wall down
├── Ward report            → bulwark ward
├── Raise Aegis / Aegis protect → sudo bulwark aegis apply desktop (+ confirm)
├── Release Aegis / Aegis release → sudo bulwark aegis undo
├── Purity photo           → bulwark purity baseline
└── Purity check           → bulwark purity check

Seal is not Bulwark (glass vs house). Never say "doctor" / healthcheck to humans.
```

Capital Ward/Aegis/Purity may be case-insensitive in the human parser.

### Alchemy (craft — packages)

```
alchemy / brew / sip / distill
human
└── brew alchemy firefox   → alchemy brew firefox   (on point; keep)
```

### Pixie (aware — agent)

```
pixie "…"
human
├── pixie "…"              → already speech-like
└── ask pixie …            → optional later
```

### Goblin (mail)

```
goblin / goblin sync / …
human — TBD (sync goblin? check goblin mail?)
```

### Ether (network)

```
ether / status ether / whisper ether
human — partly exists (`status ether`); expand carefully
```

### Raven (planned RSS — messenger)

```
raven                      → not shipped
human (intent)
└── send raven with "…"    → raven publish|post …   [when built]
```

### Scroll / Summon / Spellbook / Vault / Eye / …

TBD per app when human layer is implemented. Default: keep machine CLI; add 1–3 human aliases only when the phrase is obvious.

---

## Implementation notes (when we build the layer)

1. Registry file (TOML/JSON): `(phrase pattern) → argv[]` per app.
2. Parser: deterministic, no LLM. Fail with pink “Did you mean …?”.
3. `scroll` lists **both** human and machine forms.
4. Study order suggestion: Imp paint → Bulwark rituals → Alchemy brew → Siren aliases → messengers (Raven).

## Changelog

| Date | Note |
|------|------|
| 2026-08-16 | Doc created; Imp/Bulwark/Siren agency rules; app-by-app trees |
