# Summon — quick launcher

**Role:** dmenu-style command finder over PATH. Type a few letters, hit enter, go. System-wide ready-menu for faeOS — the inverse of `scroll` (which lists *what* exists; summon *runs* it).

**Status:** stable (v1)

## Current
- Name cache in `~/.cache/pixie/summon.list` (`name<TAB>dir`), rescanned via `summon --refresh`; auto-refreshes when stale (**6h**) or missing
- Pick (order): exact → name-startswith → token-in-name → token-in-dir; ties broken by name
- Instant type-to-filter TUI (shared `box`/`termart` layer): **↑↓ / PgUp/PgDn / Home/End** move; every printable letter filters (so `jq`/`nano` type cleanly); ^U clear, esc/q cancel; enter prints the name
- Shell wrapper in `pixie.zsh`: bare `summon` → `print -z` the pick onto the prompt (flags `-x`/`-l`/`--refresh` bypass the wrap)
- Non-interactive: `summon -l`/`--list` all names; `-x <query> [args…]` execs first match in-place (`execvpe`), **query is not re-passed as argv[1]**; remaining args pass through (`summon -x grep -c ""`)
- Pre-filter: `summon nano` opens the picker already filtered to `nano…`

## Next
- [ ] Search scope: option to also index shell aliases / functions
- [ ] MRU ordering (recently run float up) — small run-history backend
- [ ] Optional number-key jump for long lists

## Notes
- ~2.2k commands on a full Arch box; filter is keyboard-only, no mouse (`fae_termart`).
- Pure Python, no external deps; config-free — cache only.