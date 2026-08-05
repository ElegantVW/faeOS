# FaeOS Plan

**Last updated:** 2026-08-05
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
- One shared TUI layer (`fae_termart` `tui_*`), one screen policy (`pixie-screen`), one key map.
- Each app: own plan + own section in `scroll` (except easter eggs — see Kur).

## App Registry

| App | Role | Status | Plan |
|-----|------|--------|------|
| **Wizard's Tower** (faectl) | Control panel & service supervisor | stable, expand | [docs/plans/wizardtower.md](docs/plans/wizardtower.md) |
| **Scroll** | Help menu / command directory (TUI picker) | stable | [docs/plans/scroll.md](docs/plans/scroll.md) |
| **Spellbook** | File manager (TUI) | stable | [docs/plans/spellbook.md](docs/plans/spellbook.md) |
| **Ether** | Network manager (bt/wifi/lan, veil VPN, bridge hotspot) | stable | [docs/plans/ether.md](docs/plans/ether.md) |
| **Siren** | Media player (mpv, queue, playlists, trove) | stable | [docs/plans/siren.md](docs/plans/siren.md) |
| **Pixie** | Local AI assistant with tools (qwen3-4b) | stable | [docs/plans/pixie.md](docs/plans/pixie.md) |
| **Kur** | Haiku dragon — **easter egg, hidden from scroll** | stable | [docs/plans/kur.md](docs/plans/kur.md) |
| **Imp** | Terminal art generator (pixie-art lineage) | in dev (separate instance) | [docs/plans/imp.md](docs/plans/imp.md) |
| **Goblin** | Mail (aerc IMAP → local text, IDLE push) | stable | [docs/plans/goblin.md](docs/plans/goblin.md) |
| **Magpie** | Browser/search (privacy, DDG) | search stable; browse in progress | [docs/plans/magpie.md](docs/plans/magpie.md) |
| **Scry** | Command/output history (Shift-Tab visions) | stable | [docs/plans/scry.md](docs/plans/scry.md) |
| **Summon** | Quick launcher (type-to-run over PATH, dmenu-style) | stable | [docs/plans/summon.md](docs/plans/summon.md) |
| **The Eye** | Process watcher (CPU/RSS/kill) | new | [docs/plans/eye.md](docs/plans/eye.md) |
| **Vault** | Disk map (recursive sizes, ncdu-style) | new | [docs/plans/vault.md](docs/plans/vault.md) |
| **Alchemy** | Package cauldron (pacman brew/sip/distill) | new | [docs/plans/alchemy.md](docs/plans/alchemy.md) |
| **Zen** | Fullscreen browser break | stable | [docs/plans/zen.md](docs/plans/zen.md) |
| **Tome** | Document reader (Scriptorium pack) | new | [docs/plans/tome.md](docs/plans/tome.md) |
| **Tick / Termfix** | Screen tick + TTY line-edit recovery | stable | [docs/plans/tick.md](docs/plans/tick.md) |

**Infrastructure (not apps, shared):** `fae_termart.py` (shared TUI layer), `pixie-screen` (clear policy, see [docs/screen-policy.md](docs/screen-policy.md)), `menagerie` (+`menagerie-run`, `menagerie-registry.py`, `menagerie-tui.py` — AI control center: per-app llama-server instances, model registry, RAM budget, see [docs/plans/menagerie.md](docs/plans/menagerie.md)), `spellbook` (shared file picker: `--pick --output` for other apps), `ia.py` (Internet Archive engine for siren trove), `starship-*` prompt widgets, `install.sh`, systemd user units.

## Missing OS essentials (to conjure)

A normal OS ships these; faeOS doesn't (yet). Names are fae-flavored proposals — rename freely.

**Tier 1 — everyday essentials:**
| App | fae name | Role |
|-----|----------|------|
| Quick launcher | Summon ✅ | dmenu-style: type a command → run |
| Notes | Grimoire | markdown notes, pages, tags |
| Package frontend | Alchemy ✅ | pacman menu: brew (install) / sip (update) / distill (clean) |
| Task manager | The Eye ✅ | htop-like: CPU/RAM/disk/processes/kill |
| To-dos | Quests | todo.txt-style questlog, due dates |
| Clipboard history | Imbue | copy memory, re-paste |
| Screenshots | Reflection | region/window/full → gallery |
| Calculator | Abacus | REPL calc, `abacus "2+2"` from prompt |
| Disk usage | Vault ✅ | ncdu-like treasure map |
| Timer/pomodoro | Hourglass | countdowns, alarms, break (links to Zen) |
| Password manager | Crypt | pass-based, gpg vault |

**Tier 2 — strong QOL:**
| App | fae name | Role |
|-----|----------|------|
| RSS | Raven | news reader |
| Dictionary | Lexicon | offline words |
| Weather | Weatherglass | 5-day forecast |
| Calendar | Almanac | agenda + reminders |
| Image viewer | Prism | terminal images (chafa/kitty) |
| Archive manager | Coffer | zip/tar/7z with preview |
| Log viewer | Chronicle | journalctl, plain words |
| Backups | Phylactery | snapshots + restore |
| Firewall | Bulwark | rules menu |
| Bookmarks | Lore | front-end for Magpie |
| eBook reader | Tome ✅ (docs now; epub next) | reads markdown/text, epub planned |
| QR codes | Sigil | wifi creds etc. in seconds |
| File search | Seek | instant home-wide search |

**Tier 3 — flavor + niche:** Mantle (theme switcher), Tales (podcasts, or into Siren), Tongues (offline translate), Gale (speed test), Lunacy (moon), Proverbs (login motd), Hearth (IRC), Immolation (secure wipe), Puppeteer (systemd unit manager), Scriptorium (screen record).

**Infra gaps (not apps):** clipboard daemon, tmux defaults, autologin + silent boot, LUKS setup, pipewire tuning — the installer layer (Phase 2).

## Roadmap

### Phase 1 — Hardening (current)
- [x] Shared `tui_*` layer on all TUIs (ether, siren, scry, goblin, spellbook, scroll)
- [x] LLM RAM management: menagerie v2 — per-app instances, budget + eviction (replaces sleep-idle; see [docs/plans/menagerie.md](docs/plans/menagerie.md))
- [x] Tests for shared layer + key map (`tests/test_fae_termart.py`, 47 cases)
- [ ] Per-app plans maintained; wizard first-run flows
- [ ] Error handling passes (lost tty, pipe mode, KeyboardInterrupt) — mostly done via `tui_cleanup`

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

- **2026-08-05 (alchemy progress)** — **Alchemy sip no longer looks hung.** Privileged runs: `sudo -v` on the real tty first, then stream `sudo -n pacman` with a Siren-style panel — phase name, █░ fill (package n/m, download %, or phase ladder), **elapsed clock that ticks every 250ms even when pacman is silent**, last line + short log tail. Pulse marquee while waiting. Covers brew/pour/sip/distill.
- **2026-08-05 (alchemy)** — **Alchemy v1: pacman cauldron.** TUI: local installed list + search view (tab), filter/query (`/`), brew (`i`/enter) / pour (`d`) / sip (`u` = -Syu) / distill (`c` = -Sc) each with y/n then drop to tty for `sudo pacman` (password ok) and re-enter. CLI: `list` `search` `brew` `pour` `sip` `distill`. Height-budgeted layout. Registered scroll + [docs/plans/alchemy.md](docs/plans/alchemy.md); Tier-1 Alchemy marked done.
- **2026-08-05 (vault delete)** — **Vault: delete with confirm.** `d` on a row → yellow confirm `delete dir|file name (size)? y/n`; `y` unlinks files/links or `shutil.rmtree` dirs (no symlink follow into trees); refuses `/` and `$HOME`; invalidates scan cache + rescans; `n`/esc cancels. Runes + plan updated.
- **2026-08-05 (vault)** — **Vault v1: disk treasure map.** ncdu-style TUI: recursive dir sizes (no symlink follow), % of parent, dive/parent, sort size↔name, filter, hidden toggle, rescan, FS free/used bar. Scan cache by mtime; progress “weighing i/n”; partial mark on timeout. Height-budgeted layout (eye lessons). One-shot `vault list [N] [path]`. Distinct from Spellbook (browse/CRUD/pick vs weigh trees). Registered scroll + [docs/plans/vault.md](docs/plans/vault.md); Tier-1 Vault marked done.
- **2026-08-05 (the eye)** — **The Eye v1: process & system watcher.** Live TUI over `/proc`: system header (load · mem bar · avail), process table (PID · CPU% · RSS · state · cmdline), sort cpu/mem/pid/name (`s` or `1234`, `r` reverse), `/` filter mode, space pause, `k`/`K` SIGTERM/SIGKILL with y/n confirm (refuses self). Sticky selection by pid across refreshes; CPU% from jiffie deltas. One-shot: `eye list [N]`. Shared `fae_termart` layer. Registered scroll SYSTEM + [docs/plans/eye.md](docs/plans/eye.md); Tier-1 The Eye marked done.
- **2026-08-05 (summon land)** — **Summon hardened + shell-wired.** Fixes: (1) `-x <query> args…` no longer re-passes the query as argv[1] (`execvpe(name, [name]+args)`); (2) bare `summon <query>` pre-filters the picker (flags are no longer confused with the query); (3) ^U clear works (`ctrl-u`, matching termart); (4) letters always filter — arrows only for move (so `jq`/`nano` type cleanly). `pixie.zsh` wrappers: `summon` / `scroll` put the pick on the prompt via `print -z` (list/exec/refresh bypass). Scroll: spellbook blurb fixed; ^U clear. Registry status → stable; Tier-1 Summon marked done.
- **2026-08-05 (summon)** — **Summon v1: dmenu-style quick launcher over PATH.** Name cache at `~/.cache/pixie/summon.list` (auto-refresh 6h / missing, `--refresh` to rescan; 2,286 commands on this box). Type-to-filter TUI on the shared `fae_termart` layer (enter prints, `-x` runs). Match order: exact → name-startswith → token-in-name → token-in-dir. Registered in scroll SYSTEM section + [docs/plans/summon.md](docs/plans/summon.md).
- **2026-08-05 (Phase 1 tests)** — **First test suite: `tests/test_fae_termart.py` (47 cases)** covering the two shared-layer contracts every faeOS TUI depends on: `tui_read_key` (plain keys, CSI arrows/home/end/pgup/pgdn/delete, SS3, ctrl-*, escape, timeout/EOF) and `box`/`paint_frame` geometry (constant width 44–80, unicode/ASCII frames, wrapping, pre-styled line retention, title truncation, CR-LF in raw mode). **Caught a real bug:** the CSI-gathering loop spun forever on EOF (closed tty/pipe) — `tui_read_key` now breaks on empty read. Plan docs synced to menagerie v2 (`pixie.md`, `kur.md`, registry rows, RAM-budget milestone).

- **2026-08-05 (menagerie v2)** — **Menagerie = AI control center; every AI app gets its own dedicated llama-server instance.** Old 3-profile/port-fixed design retired: each app (pixie 8080 · ask 8090 · magpie 8091 · imp 8082 · kur 8081) now owns an independent spawn via `menagerie ensure <app>` — same model can run in several instances without collisions; apps stop their own on quit. New `menagerie-registry.py` (models + per-app bindings in `~/.config/pixie/menagerie.json`), `menagerie-tui.py` (interactive den: start/stop, per-app model switching, add/remove models, RAM budget), `menagerie set <app> <model>`, `models add --hf` (asks before installing the hf CLI, handles token login, `HF_HUB_DISABLE_XET=1`). **RAM budget**: suggested from hardware on first open (no AI; 7.5 GB box → 5.0 GB), editable in TUI or `menagerie budget`; `ensure` evicts idle instances when the budget is exceeded. systemd `menagerie.service` retired (ask/magpie/pixie/kur-server/imp all moved off `systemctl`; faectl → `menagerie restart pixie`). **Also fixed en route:** kur-server cold-start now waits for the model to load instead of falling back to the canned haiku; menagerie no longer uses `fuser -k` (stops only its own pids, warns on foreign port holders).

- **2026-08-04 (bottom-up chat)** — **Pixie chat now flows bottom-up with a pinned prompt box**: (1) chat content anchors to the bottom — blank rows pad *above* the newest message, so bubbles grow upward and hug the input box instead of floating mid-screen; (2) full-height frames no longer scroll — `paint_frame` skipped the trailing newline when the frame fills the terminal, which was pushing every frame up one row (top border lost, prompt box buried on shorter terminals). Verified at 53×24 (top border, prompt box, Runes footer, bottom border all on screen; live reply `Thought for 10.94s`; clean `q` quit) and 53×20 (whole frame still fits, prompt box visible).
- **2026-08-04 (UI overhaul)** — **Pixie chat rebuilt to the user's mock**: sections-based compose with viewport scroll (`↑↓`/`PgUp`/`PgDn`, auto-clamped), manual outer frame (root-caused the broken right edge: nesting `art.box(width=tw)` re-wrapped full-width lines → truncated `…`; now `│ … │` padding with `gap = tw-4`), outer title `╭─ ✦ Pixie ✦ <mode> ✦ ─╮`, user bubble left / **Pixie bubble right with `✦ Thought for Xs ✦`** (duration captured in `worker()` instead of wall-clock), full-width prompt box showing live `buf` (`✦ <text>`), Runes footer `^r ✦ Chat ✦ Deep ✦ Build ✦ Plan · esc · q`. Bare `r`/`R` no longer switch modes (typed `r` was being eaten — footer says `^r`); `ctrl-r`/`tab` cycle. Fixed `UnboundLocalError` (duplicate `input_box` assignment), space-key input, `ctrl-r` mapping in `fae_termart.tui_read_key`.
- **2026-08-04 (menagerie = AI control center)** — **All AI under `menagerie`; AI apps independent** per user directive: (1) legacy `pixie-llm`/`pixie-llm-run` names are now symlinks to `menagerie`/`menagerie-run`; (2) **kur no longer depends on imp's server** — the kur voice daemon moved 8081 → **8083** and now calls menagerie's own `kur` profile (smollm2, 8081), self-healing with `menagerie start kur`; `kur` CLI + `kur-server.service` updated, `ExecStopPost` unloads the kur profile; (3) **RAM lifecycle**: quitting pixie chat stops `menagerie.service` (qwen unloaded — `systemctl` stop, since `Restart=on-failure` would revive a plain kill), imp TUI quit runs `menagerie stop imp` (8082 freed), kur-server stop unloads kur; `ask`/`magpie` auto-start menagerie on demand; `faectl` now delegates LLM/Kur status to `menagerie status` and `restart-llm` to `systemctl --user restart menagerie.service`; `llm_up` accepts 503 (model asleep) so launch is instant. Cold-start UX: TUI opens first, "waking the menagerie brain…" phase, queued enter auto-sends once loaded. Verified end-to-end under pty: cold start → typed text visible live → queued message sent → `Thought for 24.31s` reply → quit unloads qwen, RAM freed; kur haiku via its own smollm2 profile; imp ctrl-c → 8082 gone.
- **2026-08-04 (qwen3)** — **Pixie's model upgraded to qwen3-4b** (unsloth 2507 Q4_K_M, 2.5GB, `qwen3-4b-instruct-q4_k_m.gguf`). Root-caused the stalled downloads: my `pkill -f` patterns were killing their own shells, and hf's xet transfer hangs here — `HF_HUB_DISABLE_XET=1` restores the 8-stream HTTP download (~5.8MB/s, done in 6 min). `menagerie-run` + `menagerie` now prefer qwen3-4b, fall back to qwen2.5-3b/coder; pixie's `API_URL` follows `PIXIE_LLM_PORT`. Verified: Build-mode TUI created a real file (`write_local_file` first try, byte-exact), self-corrected an unknown `uname` call into `read_local_file /proc/version` (real path, grounded answer), one-shot still fine. Tool armor now only catches rare slips instead of every turn.
- **2026-08-04 (runes)** — **Pixie chat grows Runes** (agent modes, `r`/`tab` to switch): Chat / Deep (internet research w/ sources) / Build (coding agent) / Plan (investigate-only). Dynamic content-sized bubbles, `╭─ ✦ Runes ✦ ╮` footer, per-mode system prompts with a shared cute pixie persona (playful before/after, pure-JSON tool calls). Chat migrated to `/v1/chat/completions` (proper roles incl. `tool`). Small-model armor: narrated tool calls extracted from prose, Cline-style tool/arg aliases (`code_editor`→`write_local_file`…), corrective errors for unknown tools, 3x-repeat guard, 6-round cap. `web_research` falls back DDG html → lite → Wikipedia API (DDG bot-blocks scrapers here). **Finding: qwen2.5-coder-3b is ~30% reliable at agentic tool loops — model upgrade flagged in pixie plan** (qwen3-4b has native tool calls).
- **2026-08-04 (chat)** — **Pixie grows a classic assistant chat TUI**: bare `pixie` now launches the bubbled chat (user bubble left, Pixie bubble right with `✦ time ✦`, tool-call box centered with `thought for Xs`, live token streaming from menagerie's SSE endpoint, helper line vanishes once typing starts, esc clears / q quits / ctrl-c cancels). One-shot `pixie "…"` mode unchanged. Tool intercept reused from ask: hidden JSON intent → tool box → streamed final answer. Verified under pty harness at 53 cols with a live `manage_systemd_service` call.
- **2026-08-04** — **Spellbook** gains `--pick --output` mode (shared file picker, like Windows common dialog). **Tome** integrates it: `tome` (no args) or `tome <dir>` opens spellbook picker; `o` key in read mode opens another file via picker. `tui_suspend`/`tui_resume` bridges the TTY handoff. Infrastructure now lists spellbook as shared file picker.
- **2026-08-04 (fix)** — **Picker integration hardened** after `tome` "did nothing" on bare launch: spellbook's open/pick key was only `o`/`→`/`l` — **enter now opens/picks** (footer updated). Tome's `pick_file_via_spellbook` guards pty I/O against EIO when the child exits (previously the picked file was never read back), sizes the child pty via `TIOCSWINSZ` (forkpty starts at 0×0), and prints a real message instead of silently exiting when nothing is picked. No-TTY fallback message now says *file not found here* instead of a misleading TTY error. Verified end-to-end with a pty harness.
- **2026-08-04 (root cause)** — **`tome` silent-death on real terminal found**: the minimum-size gate (60×20) killed `tome` instantly on terminals under 61 cols — the "terminal too small" message was written to the alt screen and wiped by cleanup before it could be read. User's terminal is 53 cols. Gate lowered to 40×12 (unreachable under termart's 44×12 floors, so it never blocks) and the failure path now waits for a key + echoes to stderr instead of vanishing.
- **2026-08-04 (arrows)** — **picker keys broken in real terminal**: `pick_file_via_spellbook` called `tui_suspend()`, cooking the parent terminal (ECHO on, ICANON line-buffering) for the whole picker session — arrow keys echoed as `^[` garbage and were buffered until Enter. Removed suspend/resume (child has its own pty; parent only forwards raw bytes) and set the child pty to cbreak right after `forkpty` to close the startup echo window. Arrows now navigate live; verified at 53 cols (3× down → enter → reader opens on `Tome — faeOSplan.md`).
- **2026-08-04 (theme+back)** — **Tome themed + history**: tome was the only app not setting `PIXIE_UNICODE=1`, so its frames fell back to ASCII `+- * ... * -+` (other apps set it at startup). Now fancy `╭─ ✦ Tome — file.md ✦ ╮` like the rest of faeOS. Reader gained a back-stack: `o` opens another file (picker now starts in the current file's directory) and pushes the current doc; `b` returns to the previous file; footer + plan updated.
- **2026-08-03 (night)** — **Tome** v0.1: document reader, first of the **Scriptorium** office pack. Markdown renderer (headings/bullets/quotes/tables/code/inline), `/` search with highlight + `n/N`, Tab contents (heading jumps), dir browse mode; format registry for pdf/epub later. `box()` upgraded: pre-styled body lines now keep their colors (all apps benefit). Registered in scroll + registry + [docs/plans/tome.md](docs/plans/tome.md).
- **2026-08-03 (evening)** — AI brain renamed **pixie-llm → menagerie** (3-port: qwen 8080 · kur 8081 · imp 8082); old name kept as symlink. Mistral-7b **removed** (qwen coder is the model); `fae_termart.py` rename (shared TUI layer). Ether gained the **Conjuring** panel (live download list with siren-style bars, `<name>.size` sidecar convention). All `box()` titles now double-starred by termart (`✦ Title ✦`). Missing-OS-essentials list added to this file. Qwen2.5-Coder 3B download in progress (8 parallel streams, ~35%).
- **2026-08-03** — Single main plan created (`faeOSplan.md`), per-app plans under `docs/plans/`; ROADMAP.md folded in. App registry completed (scry/zen/tick/Wizard's Tower added to the list). Kur hidden from scroll (easter egg). LLM profiles decided: Pixie = qwen coder (2.1GB, being downloaded), Kur = smollm2-360m on 8081. LLM sleep-idle (300s) shipped in `menagerie`/`menagerie-run` + systemd unit (ctx 4096). All six TUIs migrated to shared layer (ether/scroll/siren/scry/goblin/spellbook). SIREN plan marked v1.1 (queue, playlists, repeat, progress done).
- **2026-08-02** — Initial commit of ecosystem; TUIs consolidated onto shared layer.

## Docs layout

```
faeOSplan.md                 ← THIS: single main plan (goal, registry, roadmap, log)
docs/plans/<app>.md          ← one concise plan per app
docs/screen-policy.md        ← pixie-screen clear policy (shared infra)
docs/SIREN_QUICK_START.md    ← siren dev onboarding (kept)
```
