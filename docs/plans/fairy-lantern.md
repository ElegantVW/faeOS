# Fairy Lantern — GBA emulator from scratch

**Role:** Light a fable; play a pocket world. From-scratch Game Boy Advance emulator for the wizard’s leisure.

**Status:** v0.1 scaffold (Phase 0–3 started)

## Metaphor
- You are a Wizard. Fairy Lantern is the little light when work can wait.
- Each `.gba` is a **fable**; saves will be **bookmarks**.
- Not ancient “relic” hardware — living stories on glass.

## Directives
- **From scratch** — own ARM7TDMI + bus + PPU. No mGBA / libretro cores.
- Rust single binary: `fairy-lantern`
- ROMs user-supplied only

## CLI
```
fairy-lantern <rom.gba> [--frames N] [--present] [--dump out.ppm]
fairy-lantern info <rom.gba>
fairy-lantern test
fairy-lantern tui [--dir ~/roms]
fairy-lantern run <rom.gba> …
```

## Current
- [x] ROM/header load (`info`)
- [x] ARM interpreter subset (data-proc, B/BL, LDR/STR/LDRH/STRH, LDM/STM, BX, MUL…)
- [x] Thumb interpreter subset (ALU, imm, load/store, push/pop, B/BL, BX…)
- [x] Bus map + KEYINPUT + DMA enable + timer reloads + IF clear
- [x] PPU Mode 3/4 + VBlank flag/IRQ raise
- [x] **Interactive window** (`minifb`) — `fairy-lantern spark` / `play`
- [x] **Built-in SPARK fable** — Mode 3 pixel you steer (100% playable on this emu)
- [x] Self-tests (`fairy-lantern test`)
- [ ] Mode 0 tiles + sprites (commercial ROMs)
- [ ] Saves / fuller BIOS HLE

## Data
`$XDG_DATA_HOME/faeos/fairy-lantern/` · env `FAIRY_LANTERN_ROMS`, `FAIRY_LANTERN_BIOS`

## Build
```
cd ~/faeos/fairy-lantern && ./build.sh install
```
