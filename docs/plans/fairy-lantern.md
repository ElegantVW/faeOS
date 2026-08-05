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
fairy                 # home TUI — last / SPARK / roms / open path
fairy-lantern         # same
fairy last            # re-open last .gba
fairy spark           # built-in SPARK
fairy play game.gba   # play + remember as last
fairy game.gba        # same
fairy info / test / run …
```

## Current
- [x] ROM/header load (`info`)
- [x] ARM interpreter subset (data-proc, B/BL, LDR/STR/LDRH/STRH, LDM/STM, BX, MUL…)
- [x] Thumb interpreter subset (ALU, imm, load/store, push/pop, B/BL, BX…)
- [x] Bus map + KEYINPUT + DMA enable + timer reloads + IF clear
- [x] PPU Mode 3/4 + VBlank flag/IRQ raise
- [x] **Interactive window** (`minifb`) — `fairy spark` / `play`
- [x] **Built-in SPARK fable** — Mode 3 pixel you steer
- [x] **Home TUI** on bare `fairy` — Last, SPARK, roms/, recents; **new ROMs via Spellbook** (`--pick`, arrow keys) — never type a path
- [x] **Battery saves** — detect SRAM/FLASH from ROM tags; `.sav` next to ROM; autosave dirty + flush on exit
- [x] **Savestates** — F5 save / F7 load (`.flst` under data dir)
- [x] Self-tests (`fairy test`)
- [ ] Mode 0 tiles + sprites (commercial ROMs)
- [ ] Full EEPROM bit-bang / fuller BIOS HLE

## Data
`$XDG_DATA_HOME/faeos/fairy-lantern/` · `last.txt` · `recents.txt` · `roms/` · `saves/` · `states/`  
Battery: `<rom>.sav` beside the cart when possible.  
env: `FAIRY_LANTERN_ROMS`, `FAIRY_LANTERN_BIOS`, `FAIRY_LANTERN_DIR`

## Build
```
cd ~/faeos/fairy-lantern && ./build.sh install
```
