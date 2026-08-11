# Fairy Lantern — GBA emulator from scratch

**Role:** Light a fable; play a pocket world. From-scratch Game Boy Advance emulator.

**Status:** v0.10 — dual-rate FIFO (no sticky SFX), OBJ mosaic, semi-OBJ blend, battle UI

## Directives
- **From scratch** — own ARM7TDMI + bus + PPU. No mGBA / libretro cores.
- Rust: `fairy-lantern` / `fairy`
- ROMs user-supplied only

## Play
```
fairy play game.gba
```
| Key | Action |
|-----|--------|
| Arrows / WASD | D-pad |
| Z / Space | A |
| X | B |
| Enter | Start |
| P / F5 / F7 / Esc | Pause / savestate / load / quit |

## Core surface (robustness targets)
- [x] ARM + Thumb interpreter (commercial-class subset)
- [x] IRQ banking + BIOS IRQ HLE + IntrWait/Halt
- [x] DMA imm / VBlank / HBlank / FIFO special
- [x] Timers with prescale remainder + cascade
- [x] BIOS SWI: memory, decompress (LZ/RL/Huff), Div, ArcTan, AffineSet, SoundBias, m4a sound-driver family (silent)
- [x] Sound FIFO A/B sinks + SOUNDCNT master bit (silent audio, games keep running)
- [x] PPU Mode 0–5, priority composite, alpha + brightness, WIN0/1 + OBJ window, mosaic BG
- [x] FLASH1M / FLASH / SRAM battery + savestates
- [x] Keypad IRQ (KEYCNT)
- [x] DirectSound FIFO → host audio (`aplay`/`pw-cat` at GBA rate, ALSA resamples)
- [x] 1:1 sample path + silence on underrun (no held/repeated samples)
- [x] Cartridge GPIO RTC (SIIRTC) + window title clock
- [x] GBA frame pacing (~59.73 Hz)
- [x] EEPROM bit-bang (512B / 8K, auto address width)
- [x] PSG square / wave / noise mixed with DirectSound
- [x] Approximate fetch waitstates (WAITCNT + EWRAM)
- [x] Open-bus on unmapped / past-ROM reads
- [x] Halt wakes on any IE∧IF (not VBlank-only); IntrWait early-out
- [x] Timer enable 0→1 reloads counter; multi-overflow tick
- [x] Affine OBJ-window pixel-accurate mask
- [x] Dual-timer DirectSound A/B + underrun silence (no sticky SFX hold)
- [x] OBJ mosaic + identity-affine fallback (HP bars / battle HUD)
- [ ] Sequential ROM timing / remaining battle edge cases

## Liquid Crystal (BPRE) checkpoint
| Feature | Status |
|---------|--------|
| Title art | ✓ |
| Dialogue | ✓ |
| Walk + camera | ✓ |
| Sound systems m4a | DirectSound FIFO → host (~13.4 kHz for BPRE) |
| unk_ops / unknown SWI | 0 on boot→play path |
| Full playthrough | in progress |

## Build
```
cd ~/faeos/fairy-lantern && ./build.sh install
```
env: `FAIRY_DEBUG=1` for PPU register dump on headless runs.
