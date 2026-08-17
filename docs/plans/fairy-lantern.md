# Fairy Lantern — GBA emulator from scratch

**Role:** Light a fable; play a pocket world. From-scratch Game Boy Advance emulator.  
**Status:** v0.11.0 — LC boots, music, FLASH save, fights, pad + turbo  
**Repo:** [ElegantVW/fairy-lantern](https://github.com/ElegantVW/fairy-lantern) → clone to `~/fairy-lantern`

Listenable-audio restore: `git checkout sacred/sound-working` in that repo.  
Accuracy: `docs/AUDIT.md` in the independent repo.  
Vendor tree under `faeos/fairy-lantern` was **removed** — do not recreate.

## Directives

- **From scratch** — own ARM7TDMI + bus + PPU. No mGBA / libretro cores.
- Rust binaries `fairy` / `fairy-lantern` — **not** committed to faeOS git
- ROMs user-supplied only

## Plug into faeOS

```bash
git clone git@github.com:ElegantVW/fairy-lantern.git ~/fairy-lantern
cd ~/fairy-lantern && ./build.sh install
fairy play game.gba
```

Contract: [docs/engines.md](../engines.md).

## Play (summary)

| Key | Action |
|-----|--------|
| Arrows / WASD | D-pad |
| Z / Space / J | A |
| X / K | B |
| Q / E | L / R |
| Enter / RightShift | Start / Select |
| P / F5 / F7 / F6 / Esc | Pause / save / load / autosave / quit |
| C / V | Turbo on-off / 2×–4× |

## Liquid Crystal (BPRE) checkpoint

| Feature | Status |
|---------|--------|
| Title art / dialogue / walk | ✓ |
| Intro / title music | ✓ (`sacred/sound-working` baseline) |
| FLASH save | ✓ |
| Fights (HP/EXP HUD) | ✓ |
| Full playthrough | in progress |

## Env

`FAIRY_DS=a|b`, `FAIRY_AUDIO=sine`, `FAIRY_AFFINE_COMPAT=1`, `FAIRY_MIX_STAT=1` —
see the fairy-lantern README / AGENTS.md.
