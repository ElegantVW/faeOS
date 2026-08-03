# FaeOS Roadmap

**Last updated:** 2026-08-03
**Status:** Active

## Objective

FaeOS becomes a **robust CLI/TUI-first Arch-based distro** that is:

- **Privacy-focused** — offline LLM (llama.cpp via Pixie), local-only mail (goblin), private search (DuckDuckGo via Magpie), no telemetry, no cloud accounts.
- **Extremely user-friendly** — 100% plug-and-play: one installer, sane defaults, systemd units that just work, every tool discoverable in the TUI help (`scroll`).
- **Offline-first** — everything works without a network; online features (trove media, mail, search) degrade gracefully.

Current state is a working script/hook/config ecosystem on **Arch + kmscon** — not yet a distro. This roadmap bridges that gap.

## Current State (done)

- Shared TUI layer in `pixie_termart.py` (`tui_open_tty` / `tui_begin` / `tui_read_key` / `tui_cleanup` / `tui_screen_hold` / `tui_suspend` / `tui_resume`): **all six TUIs** (ether, siren, scry, goblin, spellbook, scroll) run on it — one key-map, one hold policy, one teardown.
- Screen-clear policy via `pixie-screen` holds (see `docs/screen-policy.md`).
- **Pixie** — local agent (llama.cpp, `pixie-llm`).
- **Siren** — mpv-backed player TUI: queue, playlists, shuffle/repeat, EQ waves, trove (Internet Archive) search/download.
- **Kur** — haiku bard (local LLM + TTS).
- **Scry** — command/output history (Shift-Tab).
- **Ether** — network weaves: bluetooth/wifi/lan TUI, `veil` VPN toggle, `bridge` hotspot boot fallback, `status` one-shot.
- **Goblin** — mail spirit: aerc IMAP → local text, IDLE push + timer safety net, TUI.
- **Magpie / duck** — private web search.
- **Spellbook** — file-manager TUI. **Scroll** — themed help/command picker.
- `install.sh --with-libs`; systemd user units; kmscon support.

## Roadmap

### Phase 1 — Hardening (short-term)
- [ ] Error handling: every TUI re-enters the shell cleanly (KeyboardInterrupt, lost tty, pipe mode) — partially done via shared `tui_cleanup`.
- [ ] Test suite for the shared layer + key mappings.
- [ ] Config persistence for Siren (volume, theme, repeat) and Spellbook (sort, hidden).
- [ ] Fuzzy search for Siren; metadata caching.

### Phase 2 — Distro (weeks/months)
- [ ] Package faeOS as an Arch ISO / spin (archiso or calamares): default installs the whole ecosystem.
- [ ] First-run setup wizard (TUI): user name, music dir, mail account, hotspot env, optional LLM download.
- [ ] `faectl` grows: upgrade, diagnose, logs.
- [ ] All units shipped and enabled by default; zero manual config on a fresh box.
- [ ] README install becomes: boot ISO → run wizard → done.

### Phase 3 — Polish
- [ ] Performance: start-up latency of TUIs, tick cost.
- [ ] Accessibility: bigger fonts option, reduced-motion, high-contrast theme.
- [ ] Community: CONTRIBUTING.md, CHANGELOG.md, plugin seam.

## Privacy guardrails (never broken)

- Offline LLM is the default; nothing dials home.
- Secrets never committed: `~/.config/ether/netherweave.env` (chmod 600), mail URLs with passwords, `auth.json`, Wi-Fi passwords — see README notes.
- Search only via DuckDuckGo (no trackers); media from Internet Archive (respect ToS).
- No telemetry, no analytics, no accounts.
- If a feature would require cloud sync or phone-home, it is an **anti-goal** and stays out.

## Anti-goals

- GUI-only path, mobile apps, cloud sync, streaming-service accounts (Siren stays on local files + free archives).
