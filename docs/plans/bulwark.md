# Bulwark — first-party host protection

**Role:** Firewall (Aegis), integrity (Purity), watch (Sentinel), hunt (Ward).  
**Status:** v0.1 Phase‑1 MVP (Rust, zero *security product* package deps)  
**Repo:** [ElegantVW/bulwark](https://github.com/ElegantVW/bulwark) → clone to `~/bulwark`

## Directives

- No ufw / nft CLI / clamav / fail2ban at runtime
- Kernel talk: raw `NETLINK_NETFILTER` (nf_tables) written in-tree
- Language: **Rust** single binary — **not** committed to faeOS git
- Installable / removable: `bulwark install` / `uninstall [--purge]`

## Plug into faeOS

```bash
git clone git@github.com:ElegantVW/bulwark.git ~/bulwark
cd ~/bulwark && ./build.sh install
# binary → ~/.local/lib/faeos/bulwark ; launcher → ~/bin/bulwark
```

Contract: [docs/engines.md](../engines.md). Canonical docs: repo `README.md`.

## Layers

| Layer | What |
|-------|------|
| **Sentinel** | `/proc/net/*` listeners → PID/comm (no ss) |
| **Aegis** | Policy DSL → netlink nf_tables table `bulwark`; apply/undo; deadman confirm |
| **Purity** | SHA-256 baselines; change/SUID detection |
| **Ward** | Hostile patterns (PATH writable, LD_PRELOAD, deleted exe, tmp timers) |

## CLI

```
bulwark                  # TUI
bulwark status|ports|ward
bulwark aegis show|status|apply <profile>|confirm|undo
bulwark purity baseline|check
bulwark install|uninstall [--purge]
```

Profiles (embedded): `desktop`, `strict`, `server-ssh`.

## Apply (root)

```
sudo bulwark aegis apply desktop
bulwark aegis confirm    # within deadman window (~90s)
sudo bulwark aegis undo  # remove table
```

## State

`$XDG_DATA_HOME/faeos/bulwark/` (or `BULWARK_DIR`)

## Next

- [ ] IPv6 rule parity tests in netns
- [ ] Address-from match in Aegis (src IP)
- [ ] Purity progress UI
- [ ] Static musl release CI
