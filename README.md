# pixie-kit

Personal **offline-first** terminal kit: pink Starship prompt box, local **Pixie** agent (llama.cpp), music controls, legal media search (`ether`), privacy search (`duck`), optional mail via aerc.

Works on **Linux** (Arch-tested). Not a full distro — scripts + shell hooks + configs.

## What you get

| Command | Purpose |
|---------|---------|
| `pixie "…"` | Local agent (files + tools); needs `pixie-llm` |
| `pixie-llm start\|stop\|status` | Offline llama.cpp on `127.0.0.1:8080` |
| `duck …` / `duck -a …` | DuckDuckGo via ddgr (+ optional local AI) |
| `ether list 10 music lofi` | Legal free media from Internet Archive |
| `play` / `next` / `prev` / `volume` | mpv music + PipeWire volume |
| `tick` / `up` | Screen tick + re-show last Pixie reply |
| `pixie-mail` | Sync aerc IMAP → `~/.cache/pixie/mail/` |
| `cmds` | Help list |
| `router` | Optional home-router helper (Huawei/VDF) |

Prompt: framed status box (user · idle · music · RAM/CPU/HDD) + summon line + `>`.

## Quick install

```bash
cd ~/pixie-kit   # or clone/copy this tree
chmod +x install.sh
./install.sh --with-libs          # copy tools + configs + zsh hook
# optional auto LLM on login:
./install.sh --with-libs --enable-llm
exec zsh
```

### Model (required for Pixie)

Place a **GGUF** (e.g. Mistral-7B-Instruct Q4) at:

```text
~/.local/share/pixie/models/mistral-7b-instruct.gguf
```

Or set `PIXIE_LLM_MODEL=/path/to/model.gguf`.

Then:

```bash
pixie-llm start
# or: systemctl --user enable --now pixie-llm
pixie "hello"
```

### Dependencies

| Package | Why |
|---------|-----|
| `zsh` | Shell integration |
| `python3` | Most tools |
| `starship` | Prompt |
| `llama-cpp` **or** bundled `~/.local/lib/pixie` | Offline LLM server |
| `mpv` | Music |
| `ddgr` | `duck` search |
| `curl` / `aria2c` | `ether` downloads |
| `aerc` | Optional email |
| `wpctl` (PipeWire) | `volume` |

Arch examples:

```bash
sudo pacman -S zsh starship python mpv curl
# llama.cpp server:
sudo pacman -S llama-cpp
# search:
# yay -S ddgr   # or install ddgr another way
```

## Layout

```text
pixie-kit/
  bin/           # install → ~/bin
  config/        # starship.toml, palette.env, tick.default
  shell/pixie.zsh
  systemd/pixie-llm.service
  install.sh
  README.md
```

**Not shipped:** secrets, `~/.cache/pixie`, aerc passwords, router creds, multi‑GB GGUF weights.

## Privacy

- **Pixie / ask** talk to **localhost llama.cpp only** (no cloud LLM).
- **Tools** you invoke may still use the network (`duck`, `ether`, `pixie-mail`, `web_search`).
- Bind address is **`127.0.0.1`** — not exposed on LAN by default.

## Mail (optional)

Configure [aerc](https://aerc-mail.org/) (`~/.config/aerc/accounts.conf`). Then:

```bash
pixie-mail sync
pixie "check my emails"
```

## New machine checklist

1. Copy/clone `pixie-kit`
2. `./install.sh --with-libs`
3. Install deps + GGUF
4. `systemctl --user enable --now pixie-llm` (optional)
5. `exec zsh` → `cmds` → `pixie "hi"`

## License

Personal kit — use and fork freely. Third-party models/media keep their own licenses.
