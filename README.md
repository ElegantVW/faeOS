# FaeOS

A pink, **offline-first** terminal ecosystem: framed status prompt, local **Pixie** agent (llama.cpp), **Siren** media player, **Kur** haiku bard, **Scry** history, **Ether** network weaves, **Magpie** privacy search — all wrapped in a cute fae-colored status box.

Works on **Linux** (Arch + kmscon tested). **Source-only kit** — scripts, shell hooks, configs, and thin launchers. Rust engines (Bulwark, Fairy Lantern, Seal, …) are built on the machine; see [docs/engines.md](docs/engines.md).

Single main plan: [faeOSplan.md](faeOSplan.md). Per-app plans: [docs/plans/](docs/plans/). Design: [docs/design.md](docs/design.md). CLI voice: [docs/cli-voice.md](docs/cli-voice.md).

**Terminal-first:** keyboard and CLI remain the hero path; mouse on TUIs is optional sugar. Pink crystal frames (`fae_termart`) unify the look.

## Quick install (second machine)

```bash
git clone git@github.com:ElegantVW/faeOS.git ~/faeos
cd ~/faeos
chmod +x install.sh
./install.sh --with-libs
# optional: compile greeter/terminal crates
# ./install.sh --build
exec zsh
```

### Plug-and-play engines

```bash
# Host protection
git clone git@github.com:ElegantVW/bulwark.git ~/bulwark
cd ~/bulwark && ./build.sh install

# GBA emulator
git clone git@github.com:ElegantVW/fairy-lantern.git ~/fairy-lantern
cd ~/fairy-lantern && ./build.sh install
```

After that, `bulwark` and `fairy` work with no path edits. Full contract: [docs/engines.md](docs/engines.md).

If trees already live at `~/bulwark` and `~/fairy-lantern`:

```bash
cd ~/faeos && ./install.sh --build --build-engines
```

## Commands

| Command | Purpose |
|---------|---------|
| `pixie "…"` | Local agent (files + tools); summons its own llama-server |
| `menagerie` | AI control center (TUI): models, per-app bindings, RAM budget |
| `menagerie status all` / `set <app> <model>` / `models` / `budget` | Which model each app uses, switching, add/remove models |
| `siren` | Interactive media player TUI (arrow keys) |
| `siren play` / `next` / `prev` / `stop` / `pause` / `now` | Music controls (recursive `~/Music`) |
| `siren trove 10 music lofi` | Free & legal media (Internet Archive) |
| `siren trove get <id>` | Download one archive item to `~/Music/trove` / `~/Videos/trove` |
| `magpie …` / `duck …` | Privacy search via DuckDuckGo (`duck` → magpie) |
| `kur` | Haiku bard (local LLM + TTS voice) |
| `goblin` | Mail spirit — interactive TUI, aerc IMAP → local text |
| `goblin sync` | Instant new-mail push (IMAP IDLE watcher) + 5-min timer safety net |
| `faectl` | FaeOS control panel (status / restart-llm) |
| `ether net` / `ether veil [on\|off]` / `ether bridge` | Connectivity / VPN / phone-hotspot boot fallback |
| `ether` | Live TUI: bluetooth · wifi · lan |
| `status ether` | One-shot report: bluetooth · wifi · lan |
| `scry` / Shift-Tab | Command + output history (visions) |
| `zen` | Fullscreen browser break (X one-shot / VT) |
| `scroll` | Command scroll — fae spell tabs + PATH launcher |
| `summon` / `summon -x <query>` | PATH tab of scroll (dmenu-style; `-x` runs first match) |
| `eye` / `eye list 15` | The Eye — process watcher (CPU · RSS · kill) |
| `vault` / `vault list ~` | Vault — disk map (recursive sizes) |
| `alchemy` / `brew` / `sip` / `distill` | Alchemy — pacman UI |
| `grimoire` / `grimoire new …` | Grimoire — markdown notes under `~/notes` |
| `abacus` / `abacus "2+2"` | Abacus — calculator |
| `quests` / `quests add …` | Quests — todo.txt log |
| `hourglass` / `hourglass 25` | Hourglass — timer / pomodoro |
| `almanac` / `almanac today` | Almanac — calendar hub |
| `bulwark` / `bulwark status` | Bulwark — firewall, integrity, hunt (**external repo**) |
| `fairy play game.gba` | Fairy Lantern — GBA from scratch (**external repo**) |
| `seal` / `hearth` / `rift` | Greeter / guest session / terminal (**build with `--build`**) |
| `spellbook` | File-manager TUI |
| `tick` / `termfix` | Screen tick + TTY line-edit recovery |

### Suite map

| Name | Domain |
|------|--------|
| **Pixie** | Local AI agent |
| **Siren** | Music + free archives |
| **Kur** | Haiku + TTS voice |
| **Scry** | Past commands / replies |
| **Ether** | Network paths / hotspot |
| **Magpie** | Private web search |
| **The Eye** | Processes / CPU / RAM |
| **Vault** | Disk usage map |
| **Alchemy** | Packages (pacman) |
| **Grimoire** | Notes (markdown) |
| **Abacus** | Calculator |
| **Quests** | Todos (todo.txt) |
| **Hourglass** | Timer / pomodoro |
| **Almanac** | Calendar hub |
| **Bulwark** | Protection (external: ElegantVW/bulwark) |
| **Fairy Lantern** | GBA emulator (external: ElegantVW/fairy-lantern) |

Prompt: framed pink status box (user · mood · music · RAM/CPU/HDD/temp) + `>`.

### Model (Pixie)

```text
~/.local/share/pixie/models/qwen3-4b-instruct-q4_k_m.gguf
```

Then: `menagerie status all` and `pixie "hello"`. Each AI app owns its own
llama-server instance on its own port (pixie 8080 · ask 8090 · magpie 8091 ·
imp 8082 · kur 8081), bound to a model of its own — switch with
`menagerie set <app> <model>`, add models with `menagerie models add`.

## Notes

- Music uses **mpv** IPC at `/tmp/siren-mpv.sock` (prompt + tick integration).
- Mail uses **goblin** (`~/.cache/goblin/mail`); instant push: `systemctl --user enable --now goblin-idle.service`.
- Archive.org needs working **IPv4 HTTPS** on many ISPs; `ether net` diagnoses.
- kmscon-friendly flags: `PIXIE_NO_AUTOSUGGEST=1`, `termfix`.
- Do **not** commit Wi‑Fi passwords, router creds, mail URLs with passwords, or `auth.json`.
- Do **not** commit prebuilt ELFs, GGUF weights, or GBA ROMs.

## License

MIT — see [LICENSE](LICENSE). Respect archive.org and site ToS for free media.
