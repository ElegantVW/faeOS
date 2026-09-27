# 🎵 SIREN — media player

**Status:** the house player is the **Rust engine**, [`ElegantVW/siren`](https://github.com/ElegantVW/siren).

The Python single-file player that used to live at `faeOS/bin/siren` was
**removed on 2026-09-27**. This file used to be a 267-line development plan for
it; that plan described a program the house no longer ships, so it went with
the program. Siren's own README and CHANGELOG live in its repo.

## Install

The kit does not install Siren. Build it from its repo:

    git clone https://github.com/ElegantVW/siren ~/siren
    cd ~/siren && ./build.sh install

`build.sh` puts the binary in `~/.local/lib/faeos/siren` and a thin launcher in
`~/bin/siren`.

## Why the Python player went

It was a deliberate fallback, not an accident — `siren/build.sh` refused to
overwrite it and the old plan documented `cp ~/faeOS/bin/siren ~/bin/siren` as
the rollback. But the kit's `install.sh` copies `bin/` over `~/bin`
unconditionally, so every `./install.sh` silently reverted the 2026-09-23
cutover: the 856-byte Rust launcher was being replaced by the 86KB Python
player. Rather than add a guard around a trap, the trap was removed.

Going with it:

- `tests/test_siren.py` (25 tests). It loaded `bin/siren` through a
  `SourceFileLoader`, so it had no subject once the player was gone. **This
  leaves Siren with 2 unit tests in `src/spectrum.rs` and no integration
  coverage** — that gap is real and is recorded in `CHANGELOG.md`.
- `docs/SIREN_QUICK_START.md`, a development guide to the Python player.

## The surface the kit depends on

`README.md` documents these, and the Rust engine implements all of them:

    siren                          interactive TUI
    siren play|next|prev|stop|pause|now
    siren queue|playlist|radio|cast
    siren trove 10 music lofi     free media, Internet Archive
    siren trove get <id>          download into ~/Music/trove, ~/Videos/trove

Music uses **mpv** IPC at `/tmp/siren-mpv.sock` for prompt and tick
integration. That path is unchanged by the migration.

The content pipeline is unaffected: `tools/content/make.sh` and
`tools/content/shots.yaml` both invoke `~/bin/siren`, which is the launcher,
not this repo's copy.
