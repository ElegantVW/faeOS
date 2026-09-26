# ElegantVW — the pink offline-first house

One person, one office box, one column of software. Everything here runs
on the machine in front of you: no cloud accounts, no telemetry, no
prebuilt blobs you can't rebuild.

## The picture

| Layer | What | Repos |
|-------|------|-------|
| Fire | Firmware + kernel we write (Kindling) | [fae-kernel](https://github.com/ElegantVW/fae-kernel) |
| Glass | Screen lock + guest + terminal | [bulwark](https://github.com/ElegantVW/bulwark) (`glass/`), faeOS `hearth/`, `rift/` (incomplete) |
| House | Firewall ward, local AI agent, music, mail, emulator, hillfort game, haiku dragon | [bulwark](https://github.com/ElegantVW/bulwark) (`house/`), [pixie](https://github.com/ElegantVW/pixie), [siren](https://github.com/ElegantVW/siren), [goblin](https://github.com/ElegantVW/goblin), [fairy-lantern](https://github.com/ElegantVW/fairy-lantern), [mourama](https://github.com/ElegantVW/mourama), [kur](https://github.com/ElegantVW/kur) |
| Suite | Pink terminal kit that ties it together | [faeOS](https://github.com/ElegantVW/faeOS) |
| Shop | Car-interior atelier software (private) | `vanguarda-automovel` (private) |

The office box is the world. Phones are windows (Tailscale + LAN).
Source-only: every engine builds on your machine with `./build.sh install`.

## Honesty statement

- Working: terminal suite, firewall ward + lock, GBA boots/saves/fights,
  mail TUI, music local + speakers, agent stack, hillfort tick, kernel phase 1.
- Holes: no cold professional review yet, hearth/rift incomplete,
  fairy-lantern is not mGBA-class, kernel has no userspace.
- No claim of nation-state defense, antivirus, or professional sign-off
  until the adversarial cards pass with SHAs.

## Install order

```bash
git clone git@github.com:ElegantVW/faeOS.git ~/faeOS && cd ~/faeOS && ./install.sh
git clone git@github.com:ElegantVW/bulwark.git ~/bulwark && cd ~/bulwark && ./build.sh install
git clone git@github.com:ElegantVW/pixie.git ~/pixie && cd ~/pixie && ./install.sh
# then: goblin, siren, fairy-lantern, mourama, fae-kernel
```

A pure manifest installer (`ElegantVW/fae`) will replace this list once tags
stabilize. Until then this page is the map.
