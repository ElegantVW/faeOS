# faeOS error voice

> House-wide rules for **what humans see when something goes wrong**.
> All ages. Creature-first. Safety and clarity over sysadmin jargon.
> Machine CLIs may still exit non-zero; this is about **wording**, not exit codes.

Companion to [cli-voice.md](cli-voice.md) (commands) and [design.md](design.md) (chrome).

## Shape (always)

```
<creature>: <one plain sentence>
  next:  <one thing to try>          # when there is an obvious next step
  detail: <rust/python chain>        # ONLY if FAE_DEBUG=1
```

| Part | Rule |
|------|------|
| **creature** | lowercase command name: `bulwark:`, `siren:`, `pixie:`, `ether:` |
| **sentence** | What happened in house language. No errno dumps as the only line. |
| **next** | Optional. Imperative, short, copy-pasteable when useful. |
| **detail** | Optional. Full chain / OS text behind `FAE_DEBUG=1`. |

TUI apps may put the same sentence inside a pink `box(..., title=Creature)` with `P.ERR` / `P.WARN` instead of a bare stderr line.

## Laws

1. **Never store or print passwords.** Elevate via `sudo` / PAM; say “password” only as “we may ask.”
2. **No devops-isms for humans:** doctor, healthcheck, EACCES, errno, NACK, netlink, nf_tables, CAP_NET_ADMIN — unless `FAE_DEBUG=1`.
3. **Name the power, not the package:** Aegis / wall / door / photo — not “firewalld failed.”
4. **Blame softly:** prefer “could not…” over “YOU forgot…”
5. **One next step** beats a paragraph of theories.
6. **Scripts still work:** stable argv and exit codes; voice is the human layer.

## Creature flavor (light)

| Kind | Tone when failing |
|------|-------------------|
| **Aware** (Siren, Pixie) | “I couldn’t…” / “Siren can’t hear the song…” |
| **Ward** (Bulwark) | “The wall…”, “Aegis…”, “Purity…” |
| **Craft** (Imp, Alchemy) | “The brew failed…”, “Imp couldn’t paint…” |
| **Path** (Ether) | “could not weave…”, “bridge failed…” (Ether already close) |

Do not over-roleplay in errors — **clarity first**, flavor second.

## Common mappings

| Underlying | Human line (examples) | next |
|------------|----------------------|------|
| Permission denied (user files) | could not write in your notes folder | fix folder ownership, or re-run the command that raises the wall |
| sudo cancelled | permission was cancelled | try again and enter your password |
| missing engine binary | engine not built yet | `cd ~/… && ./build.sh install` |
| need raise Aegis | front door is still open | `bulwark aegis apply desktop` then `confirm` |
| kernel rejected wall | Aegis could not raise the wall | `FAE_DEBUG=1` … or Release and try again |
| no TTY | needs a real terminal (not a pipe) | run in a terminal window |
| not found (command) | command not found | check `scroll` / install |

## Env

| Env | Effect |
|-----|--------|
| `FAE_DEBUG=1` | Print `detail:` with the full error chain / OS text |
| (unset) | Plain + optional `next:` only |

## Rollout

1. **Docs** — this file (seed).  
2. **Shared helper** — `fae_termart.fae_error(creature, msg, next=None)`.  
3. **Apps** — Bulwark first (Rust), then Python house apps as touched.  
4. Future session — sweep remaining strings app-by-app.

## Anti-patterns

```
# bad
bulwark: nf_tables batch NACK: Operation not supported (os error 95)

# good
bulwark: Aegis could not raise the wall
  next:  try again, or FAE_DEBUG=1 bulwark aegis apply desktop
```
