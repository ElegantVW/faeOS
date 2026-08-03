# FaeOS Plan

**Last updated:** 2026-08-03
**Status:** Active build toward v1.0 (Arch distro)
**Location:** This file is the *single* main plan. Each app has its own short plan in `docs/plans/`; this file stays concise.

## Goal

**faeOS — a complete, plug-and-play, CLI/TUI-based Arch distro, extremely user-friendly.**

- Everything is a terminal app, pink-themed, discoverable via `scroll` (help menu).
- One installer → boot ISO → wizard → done. Zero manual config on a fresh box.
- **Privacy-first, offline-first**: local LLM, local mail, no telemetry, no accounts, no cloud.

## Principles (never broken)

- Offline by default; online features degrade gracefully (trove, mail, search).
- No telemetry, no analytics, no phone-home. Cloud sync / mobile / GUI-first are **anti-goals**.
- Secrets never committed (`netherweave.env`, mail URLs with passwords, `auth.json`, Wi-Fi keys).
- One shared TUI layer (`pixie_termart` `tui_*`), one screen policy (`pixie-screen`), one key map.
- Each app: own plan + own section in `scroll` (except easter eggs — see Kur).

## App Registry

| App | Role | Status | Plan |
|-----|------|--------|------|
| **Wizard's Tower** (faectl) | Control panel & service supervisor | stable, expand | [docs/plans/wizardtower.md](docs/plans/wizardtower.md) |
| **Scroll** | Help menu / command directory (TUI picker) | stable | [docs/plans/scroll.md](docs/plans/scroll.md) |
| **Spellbook** | File manager (TUI) | stable | [docs/plans/spellbook.md](docs/plans/spellbook.md) |
| **Ether** | Network manager (bt/wifi/lan, veil VPN, bridge hotspot) | stable | [docs/plans/ether.md](docs/plans/ether.md) |
| **Siren** | Media player (mpv, queue, playlists, trove) | stable | [docs/plans/siren.md](docs/plans/siren.md) |
| **Pixie** | Local AI assistant with tools (qwen coder) | stable | [docs/plans/pixie.md](docs/plans/pixie.md) |
| **Kur** | Haiku dragon — **easter egg, hidden from scroll** | stable | [docs/plans/kur.md](docs/plans/kur.md) |
| **Imp** | Terminal art generator (pixie-art lineage) | in dev (separate instance) | [docs/plans/imp.md](docs/plans/imp.md) |
| **Goblin** | Mail (aerc IMAP → local text, IDLE push) | stable | [docs/plans/goblin.md](docs/plans/goblin.md) |
| **Magpie** | Browser/search (privacy, DDG) | search stable; browse in progress | [docs/plans/magpie.md](docs/plans/magpie.md) |
| **Scry** | Command/output history (Shift-Tab visions) | stable | [docs/plans/scry.md](docs/plans/scry.md) |
| **Zen** | Fullscreen browser break | stable | [docs/plans/zen.md](docs/plans/zen.md) |
| **Tick / Termfix** | Screen tick + TTY line-edit recovery | stable | [docs/plans/tick.md](docs/plans/tick.md) |

**Infrastructure (not apps, shared):** `pixie_termart.py` (shared TUI layer), `pixie-screen` (clear policy, see [docs/screen-policy.md](docs/screen-policy.md)), `pixie-llm` (+`pixie-llm-run`, llama.cpp profiles, sleep-idle), `ia.py` (Internet Archive engine for siren trove), `starship-*` prompt widgets, `install.sh`, systemd user units.

## Roadmap

### Phase 1 — Hardening (current)
- [x] Shared `tui_*` layer on all TUIs (ether, siren, scry, goblin, spellbook, scroll)
- [x] LLM RAM management: sleep-idle unload/reload (`PIXIE_LLM_SLEEP_IDLE`)
- [ ] Per-app plans maintained; wizard first-run flows
- [ ] Error handling passes (lost tty, pipe mode, KeyboardInterrupt) — mostly done via `tui_cleanup`
- [ ] Tests for shared layer + key map

### Phase 2 — Distro (weeks/months)
- [ ] Arch ISO / spin (archiso or calamares): installs the whole ecosystem
- [ ] Wizard's Tower first-run wizard: user, music dir, mail, hotspot env, optional model fetch
- [ ] All systemd units shipped + enabled by default
- [ ] `faectl` grows: upgrade, diagnose, logs
- [ ] Install story: boot ISO → run wizard → done

### Phase 3 — Polish
- [ ] Startup latency of TUIs; tick cost
- [ ] Accessibility (fonts, high-contrast, reduced motion)
- [ ] CONTRIBUTING.md, CHANGELOG.md, plugin seam

## Log

- **2026-08-03** — Single main plan created (`faeOSplan.md`), per-app plans under `docs/plans/`; ROADMAP.md folded in. App registry completed (scry/zen/tick/Wizard's Tower added to the list). Kur hidden from scroll (easter egg). LLM profiles decided: Pixie = qwen coder (2.1GB, being downloaded), Kur = smollm2-360m on 8081. LLM sleep-idle (300s) shipped in `pixie-llm`/`pixie-llm-run` + systemd unit (ctx 4096). All six TUIs migrated to shared layer (ether/scroll/siren/scry/goblin/spellbook). SIREN plan marked v1.1 (queue, playlists, repeat, progress done).
- **2026-08-02** — Initial commit of ecosystem; TUIs consolidated onto shared layer.

## Docs layout

```
faeOSplan.md                 ← THIS: single main plan (goal, registry, roadmap, log)
docs/plans/<app>.md          ← one concise plan per app
docs/screen-policy.md        ← pixie-screen clear policy (shared infra)
docs/SIREN_QUICK_START.md    ← siren dev onboarding (kept)
```
