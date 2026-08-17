# Engines — plug-and-play build contract

faeOS is a **source-only** kit: scripts, configs, and thin launchers in git.
Heavy Rust binaries are **built on the machine**, never committed.

This page is the canonical integration contract for:

| Engine | Repo / tree | Public command |
|--------|-------------|----------------|
| **Bulwark** | `ElegantVW/bulwark` → `~/bulwark` | `bulwark` |
| **Fairy Lantern** | `ElegantVW/fairy-lantern` → `~/fairy-lantern` | `fairy` / `fairy-lantern` |
| **Seal** | in-tree `faeos/seal` | `seal` |
| **Hearth** | in-tree `faeos/hearth` | `hearth` |
| **Rift** | in-tree `faeos/rift` | `rift` |

## Paths

| Role | Path |
|------|------|
| Public CLI | `$HOME/bin/<name>` — **always a shell launcher** |
| Installed binary | `$HOME/.local/lib/faeos/<name>` — written only by `./build.sh install` |
| Dev tree binary | `$HOME/<repo>/target/release/<name>` (or `~/faeos/<crate>/target/release/<name>`) |

## Discovery order (every launcher)

1. Env override: `BULWARK_BIN`, `FAIRY_BIN`, `SEAL_BIN`, `HEARTH_BIN`, `RIFT_BIN`
2. `~/.local/lib/faeos/<name>`
3. Sibling / known release tree (e.g. `~/bulwark/target/release/bulwark`)
4. Clear error with a one-line build hint (exit 127)

Fairy also auto-rebuilds when the source tree is newer than `target/release/fairy`.

## Second machine (recommended)

```bash
# 1. Kit (no cargo required)
git clone git@github.com:ElegantVW/faeOS.git ~/faeos
cd ~/faeos && ./install.sh

# 2. Optional engines — each is seamless after install
git clone git@github.com:ElegantVW/bulwark.git ~/bulwark
cd ~/bulwark && ./build.sh install

git clone git@github.com:ElegantVW/fairy-lantern.git ~/fairy-lantern
cd ~/fairy-lantern && ./build.sh install

# 3. In-tree greeter / guest / terminal (optional)
cd ~/faeos && ./install.sh --build
# or individually:
#   cd ~/faeos/seal && ./build.sh install
#   cd ~/faeos/hearth && ./build.sh install
#   cd ~/faeos/rift && ./build.sh install
```

Or, if sibling engine trees already exist:

```bash
cd ~/faeos && ./install.sh --build --build-engines
```

## Installer rules

- `build.sh install` copies the **ELF into** `~/.local/lib/faeos/`, never into git.
- It may place/update a **launcher script** in `~/bin` if missing, or if `~/bin/<name>` is still a leftover ELF.
- It **never** replaces a good launcher with a raw binary.
- `faeos/install.sh` copies launchers + scripts only; use `--build` / `--build-engines` to compile.

## Raise the wall (Bulwark)

Building Bulwark installs the engine only. The front-door lock stays **down** until you raise Aegis:

```bash
sudo bulwark aegis apply desktop
bulwark aegis confirm
bulwark          # look — must not say SAFE if the wall is missing
```

- **desktop** profile: no SSH; fae AI ports only on `127.0.0.1`
- **server-ssh** if you intentionally want port 22
- Seal (screen lock) is separate — glass vs house

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `engine not built yet` | `cd ~/… && ./build.sh install` |
| Wrong binary | `export NAME_BIN=/path/to/binary` or reinstall |
| Command missing | Ensure `~/bin` is on `PATH`; re-run `~/faeos/install.sh` |
| Arch mismatch | Expected — rebuild on the target machine (no prebuilt ELFs) |
| Bulwark CARE / door open | Raise Aegis (above); install alone is not enough |

## What never goes in git

- `target/`
- Prebuilt ELF under `bin/`
- `*.gba`, `*.sav`, GGUF models, secrets (`netherweave.env`, `auth.json`, …)
