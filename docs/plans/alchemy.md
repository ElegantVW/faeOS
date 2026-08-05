# Alchemy — package cauldron

**Role:** Friendly pacman front-end. Brew potions (install), sip the cauldron (upgrade), distill the dregs (cache clean).

**Status:** new (v1)

## Current
- `alchemy` — TUI on shared `fae_termart` layer; hold `alchemy`
- **Views:** local (installed, `pacman -Q`) · search (repos, `pacman -Ss`) — `tab` switches
- **Keys:** ↑↓ · `/` filter (local) or query (search; enter runs search) · `i`/enter brew · `d` pour (`-Rns`) · `u` sip (`-Syu`) · `c` distill (`-Sc`) · `r` refresh · `q`
- Confirm y/n for brew/pour/sip/distill, then leave alt-screen so `sudo` can prompt; Enter returns to TUI
- CLI: `alchemy list [q]` · `search <q>` · `brew <pkg…>` · `pour <pkg…>` · `sip` · `distill`
- Height-budgeted cauldron list (same lessons as Eye/Vault)

## Next
- [ ] Explicit package info pane (`pacman -Si` / `-Qi`)
- [ ] AUR helper optional hook (yay/paru) behind a flag — not default
- [ ] Batch select multi-brew
- [ ] Orphans list (`pacman -Qdt`) as a third view

## Notes
- Needs `pacman` + `sudo`. No root for list/search.
- Distill uses `-Sc` (uninstalled cache), not `-Scc` (full wipe).
- Does not replace `pacman` — it wraps the verbs faeOS names: brew / pour / sip / distill.
