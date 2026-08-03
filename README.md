# FaeOS

A pink, **offline-first** terminal ecosystem: framed status prompt, local **Pixie** agent (llama.cpp), **Siren** media player, **Kur** haiku bard, **Scry** history, **Ether** network weaves, **Magpie** privacy search — all wrapped in a cute fae-colored status box.

Works on **Linux** (Arch + kmscon tested). Scripts + shell hooks + configs — not a full distro yet. Single main plan: [faeOSplan.md](faeOSplan.md) (goal, app registry, roadmap, log); per-app plans in [docs/plans/](docs/plans/).

## Commands

| Command | Purpose |
|---------|---------|
| `pixie "…"` | Local agent (files + tools); needs `pixie-llm` |
| `pixie-llm start\|stop\|status` | Offline llama.cpp on `127.0.0.1:8080` |
| `siren` | Interactive media player TUI (arrow keys) |
| `siren play` / `next` / `prev` / `stop` / `pause` / `now` | Music controls (recursive `~/Music`) |
| `siren trove 10 music lofi` | Free & legal media (Internet Archive) |
| `siren trove get <id>` | Download one archive item to `~/Music/trove` / `~/Videos/trove` |
| `magpie …` / `duck …` | Privacy search via DuckDuckGo (`duck` → magpie) |
| `kur` | Haiku bard (local LLM + TTS voice) |
| `goblin` | Mail spirit — interactive TUI, aerc IMAP → local text |
| `goblin sync` | Instant new-mail push (IMAP IDLE watcher) + 5-min timer safety net; squeaks on new mail |
| `faectl` | FaeOS control panel (status / restart-llm) |
| `ether net` / `ether veil [on\|off]` / `ether bridge` | Connectivity check / VPN toggle (`vpn`) / phone-hotspot boot fallback |
| `whisper ether` / `listen ether` | Tune Bluetooth audio: ANC headphone / JBL Go 3 (each switches + sets default sink) |
| `ether` | Live TUI: bluetooth · wifi · lan — `w/l` weave, `s` scan (top 5), `n` new, `d` remove, `R` restart (soft / sudo), `r` refresh, `q` quit |
| `status ether` | One-shot report: bluetooth · wifi · lan at a glance |
| `scry` / Shift-Tab | Command + output history (visions) |
| `zen` | Fullscreen browser break (X one-shot / VT) |
| `scroll` | Themed command directory (interactive help picker) |
| `spellbook` | File-manager TUI (j/k move, ? help, n/d/r/e dialogs) |
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

Prompt: framed pink status box (user · mood · music · RAM/CPU/HDD/temp) + `>`.

## Quick install

```bash
cd ~/faeos
chmod +x install.sh
./install.sh --with-libs
exec zsh
```

### Model (Pixie)

```text
~/.local/share/pixie/models/mistral-7b-instruct.gguf
```

Then: `pixie-llm start` and `pixie "hello"`.

## Notes

- Music uses **mpv** IPC at `/tmp/siren-mpv.sock` (prompt + tick integration).
- Mail uses **goblin** (`~/.cache/goblin/mail`); instant push: `systemctl --user enable --now goblin-idle.service` (IMAP IDLE watcher), with `goblin-sync.timer` every 5 min as a safety net. Drop a sound at `~/.config/goblin/notify.mp3` to give the goblin a voice (`goblin sound --set file.mp3`).
- Archive.org needs working **IPv4 HTTPS** on many ISPs; `ether net` diagnoses; the phone hotspot bridge reads a **local** env (`~/.config/ether/netherweave.env`, chmod 600, never committed) and runs at boot via `ether-bridge.service`.
- kmscon-friendly flags: `PIXIE_NO_AUTOSUGGEST=1`, `termfix`.
- Do **not** commit Wi‑Fi passwords, router creds, mail URLs with passwords, or `auth.json`.

## License

MIT — see [LICENSE](LICENSE). Respect archive.org and site ToS for free media.
