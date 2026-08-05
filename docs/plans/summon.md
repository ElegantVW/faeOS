# Summon — quick launcher

**Role:** dmenu-style command finder over PATH. Type a few letters, hit enter, go. System-wide ready-menu for faeOS — the inverse of `scroll` (which lists *what* exists; summon *runs* it).

**Status:** new

## Current
- Name cache in `~/.cache/pixie/summon.list` (`name<TAB>dir`), rescanned via `summon --refresh`; auto-refreshes when stale (>1 day) or missing
- Pick (order): exact → name-startswith → token-in-name → token-in-dir; ties broken by name
- Instant type-to-filter TUI (shared `box`/`termart` layer): ↑↓/n/p/j/k, ctrl-u clear, esc/c-c cancel, enter print; `-x`/`--exec` turns enter into just run it
- Non-interactive: `summon -l`/`--list` all names; `-x <query>` execs first match in-place (`execvpe`), propagates exit code
- Flags are first arg only, so trailing args pass through to the picked command (`summon -x grep -c ""`)

## Next
- [ ] Search scope: option to also index shell aliases / `~/.local/bin`-adjacent trees
- [ ] MRU ordering (recently run float up) — needs a small run-history backend
- [ ] Numbers/`jk` as selection hints (rocket-launcher style) for long lists

## Notes
- 2,286 commands on this box; filter is keyboard-only, no mouse (`fae_termart`).
- Pure Python, no external deps; config-free — cache only.