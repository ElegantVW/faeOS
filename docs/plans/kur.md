# Hidden familiar (egg)

**Role:** A small local haiku/voice familiar, productized as a **hatchable quest**.  
**Status:** engine stable · leaf sealed until hatch

## Architecture (no quest solution)

| Piece | Role |
|-------|------|
| Scroll **Sealed Leaf** | Quest hook — egg in the Menagerie; points at `murmur` |
| `murmur` | Babbling glass (mostly gibberish; rare clean shards) |
| `~/.local/share/faeos/eggs/dragon.json` | Hatch flag after first successful true-name speech |
| `bin/vendor/smoltide*` | Opaque backends until cascade rename |
| `kur` / menagerie profile | True name — not taught by docs |

**Hatch:** only after the player completes the in-world tasks (wake the pen, speak the name). Murmur never hatches alone.

**Policy:** Do **not** commit solve paths, ciphers, keyword tables, or step-by-step rituals in this repo.

## Engine (post-discovery)

- Voice ~8083 · LLM profile in menagerie · small instruct model  
