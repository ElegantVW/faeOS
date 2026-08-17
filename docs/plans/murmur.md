# Murmur — the babbling glass

**Role:** Moonring-style NPC oracle for the hermetic egg quest (and a house toy).  
**Status:** Phase B+ (waves 1–4)

## Surface
- `murmur` — crystal chat with the glass (default)  
- `murmur "words"` — one exchange  
- Mostly gibberish; rare clear shards on certain offerings  
- **Never** a walkthrough; **never** hatches the egg alone  

## Feel
- Session mood (**fog / stir / clear**) + turn count in title  
- Soft **acts** (fog-heavy → stirred → thin) from meaningful hits / bond  
- Memory, tired-of-that-word, phrase cooldowns, theme threads, bond score  
- Meta-asks (`help` / `hint` / `solve`…) → mockery only  
- Silence (`?` / `...`) → micro-reactions  
- Greet / return-greet / farewell · thematic idle mutters  
- Entrance splash (visit tiers) · `--no-splash` / `MURMUR_QUIET=1`  
- Enter think-beat · exchange gap · Home/End log top/bottom (letters free for speech)  
- Wheel / PgUp log · Ctrl-L wipe · Ctrl-W word-erase · zoom-safe  
- Soft persistence: `~/.local/share/faeos/murmur/glass.json`  
- World flags (boolean only): visit / deep-turn marks for Sealed Leaf atmosphere  
- Post-hatch: slightly clearer glass (no spoilers)

## Policy
No keyword tables or solutions in docs. Quest architecture: see egg plan (no solve path).

## Why not Rust (for now)
Dialogue + pink TUI shares `fae_termart` with the rest of the house. Rust would mean a second chrome stack for little gain (not privileged, not hot-path). Revisit if murmur becomes a long-lived daemon.
