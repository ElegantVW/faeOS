# faeOS sounds

Original, license-clean assets (square/triangle PSG-style synthesis).  
Inspired by classic SNES/PS1 RPG menus and GBA-era overworld vibes — **not** ripped from Final Fantasy or Pokémon.

## UI SFX (`ui/`)

| File | Use |
|------|-----|
| `menu_cursor.wav` | Move selection |
| `menu_confirm.wav` | Accept / OK |
| `menu_cancel.wav` | Back / no |
| `menu_open.wav` | Open menu / pause |
| `menu_close.wav` | Close menu |
| `menu_error.wav` | Invalid action |
| `menu_save.wav` | Save / checkpoint |
| `menu_equip.wav` | Equip / apply item |
| `menu_levelup.wav` | Level-up sting |
| `notify_ding.wav` | Desktop / goblin notify |
| `text_advance.wav` | Dialogue next line |
| `shop_coin.wav` | Purchase / coin |
| `battle_sting.wav` | Encounter sting |
| `heal_chime.wav` | Heal / restore |

## Seal

| File | Use |
|------|-----|
| `seal-unlock.wav` | Successful unlock / greeter pass (~1.5s, syncs with fade). Original soft-PSG; floaty Dmaj9 (maj7 + 9th) — not ripped game audio. |

Canonical path: `~/faeos/assets/sounds/` (and `ui/` for menu SFX)  
Runtime copies may live in `~/.local/share/faeos/sounds/`.  
Override: `SEAL_UNLOCK_SOUND=/path/to.wav`
Siren-friendly mirror: `~/Music/faeos-ui/`

Play:
```bash
paplay ~/faeos/assets/sounds/ui/menu_confirm.wav
# or
mpv --no-video ~/Music/faeos-ui/menu_cursor.wav
```

Goblin mail notify is set to `~/.config/goblin/notify.wav` (copy of `notify_ding.wav`).

## Chiptune / ambient (`~/Music/faeos-chiptune/`)

Original GBA / gen-3-ish PSG palette (not game rips):

| File | Feel |
|------|------|
| `murmur_glass_fog.wav` | **Murmur theme** — *Glass Fog*, ~94 BPM waltz 3/4, ~2:18 full arc (interwoven PSG voices; circles for game loop). Regenerator: `faeos/tools/compose_glass_fog.py` |
| `route_calm_town.wav` | Quiet town / home |
| `route_adventure.wav` | Overworld route |
| `battle_trainer_pulse.wav` | Battle energy |
| `cave_echoes.wav` | Cave / mystery (legacy murmur pad) |
| `victory_fanfare_mini.wav` | Win sting |

```bash
paplay ~/Music/faeos-chiptune/murmur_glass_fog.wav
# or in murmur: autoplay + Ctrl-p toggle · FAE_AMBIENCE=0 silence
siren play faeos-chiptune
```

## Real Pokémon OST you already have

Personal library (not shipped with faeOS):

- `~/Music/ether/pkmn-frlg-soundtrack/` — FireRed/LeafGreen
- `~/Music/siren/pkmn-rse-soundtrack/` — a couple RSE bonus tracks

Those are copyrighted game audio for personal use; keep them out of the public repo.

## Regenerating

The generators are one-off Python in the session that created this pack.
Re-run synthesis or edit WAVs with any DAW if you want more duty-cycle grit / stereo / loop points.
