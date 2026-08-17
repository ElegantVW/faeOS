# 🚀 SIREN - QUICK START GUIDE FOR DEVELOPERS

**Purpose:** Get any agent/developer productive with Siren development in 5 minutes.

---

## 📋 IMMEDIATE ACTIONS

### 1. Understand the Current State
```bash
# See what files exist
ls -la ~/bin/siren*

# Check the main entry point (single file — CLI + TUI + engine + waves)
head -30 ~/bin/siren

# See what music is available
ls ~/Music/
```

### 2. Test Current Functionality
```bash
# Start the interactive TUI
siren

# Play some music (fuzzy — matches any track/album/path tokens)
siren play lofi
siren play "BLESS"

# Try free archive
siren trove 10 music lofi   # search Internet Archive + pick
siren trove get <id>        # download one item to ~/Music/trove or ~/Videos/trove

# Check help
siren --help
siren about
```

---

## 🎯 CURRENT STATE (v2.0 — 2026-08-05)

Siren is now a **single-file app** (`bin/siren`): `siren_player.py` and `siren_waves.py`
were merged in and deleted. New since v1.1:

- **Config persistence** — `siren config get|set <key> <value>`, stored at
  `~/.config/siren/config.json` (volume, library roots, toggles, wave bands).
- **Fuzzy search** — tiered matcher (exact → prefix → substring → all-tokens →
  subsequence) over filenames + metadata; unmatched queries now error instead of
  playing the whole library.
- **Metadata cache** — `~/.cache/siren/meta.json` (path + mtime keyed); mutagen is
  optional/lazy; filename fallback otherwise.
- **Gapless + normalization** — `gapless` (mpv `--gapless-audio=yes`) and `normalize`
  (ReplayGain-track mode) config toggles, applied at spawn.
- **Tests** — `tests/test_siren.py` (31 cases); run `python3 -m pytest tests/`.

### Quick reference
```bash
siren queue add|list|clear|play|next|remove|move
siren playlist save|load|list|remove <name>
siren config get default_volume; siren config set default_volume 90
siren play /path/to/file.flac      # direct file
siren play <playlist-name>         # saved playlist wins over fuzzy
siren random                       # shuffle the whole library
```

### TUI keys
- browser: `↑↓/jk` move · `o/enter/p/space` open/play · `backspace` up · `a` add · `/` filter
- queue: `↑↓/jk` · `enter/space` play from · `d` remove · `c` clear
- EQ: `p/space` play/pause · `n/b` next/prev · `s` shuffle · `r` repeat · `w` show/hide EQ · `W` bands · `+/-`
- global: `Tab` focus cycle · `S` save · `L` load&play · `R` rm playlist · `g` go-to · `q/esc` quit
- spellbook bridge: `f` open a file · `F` open a directory (plays all its audio) — both pick via Spellbook (`p` inside picks the current dir)

### TUI layout
- Header, optional **waves** panel, side-by-side crystal **browser** + **queue** panels, **runes** footer — same `╭─ ✦ … ✦ ─╮` chrome as the rest of faeOS.

### TUI mouse (shared `fae_termart` SGR)
- **Click** a browser/queue row to select · **double-click** to open/play
- **Click** a panel (or waves) to focus that region
- **Wheel** over a list to move the selection (under-cursor)
- Disable: `siren config set mouse false` (Shift+drag still selects text in the terminal)
- Needs mouse reporting (Kitty, Alacritty, foot, …). In tmux: `set -g mouse on`.

---

## 🛠️ COMMON TASKS

### Add a New Command
```python
# In bin/siren, main() dispatch (around line 2063):
if cmd == "mycommand":
    return my_command_handler(rest)
```

### Add a Config Key
```python
# 1. Add the field to the SirenConfig dataclass (line ~83).
# 2. Add validation in SirenConfig.load() and a branch in cli_set_config().
# 3. Document in the plan doc + quick start.
```

### Add Error Handling
```python
# Player.send/get already swallow OSError and return defaults — never spawn
# mpv on reads. New IO should follow the same pattern:
try:
    ...
except OSError:
    return default
```

---

## 📁 PROJECT STRUCTURE

### Current (What You Have)
```
bin/
├── siren           # Single file: CLI + TUI + playback engine + waves EQ
├── fae_termart.py  # Shared TUI layer (frames, paint, tui_* helpers)
├── ia.py           # Shared Internet Archive engine (siren trove delegates here)
└── kur_voice.py    # Piper TTS via the same mpv socket (SIREN_SOCK override)

~/.config/siren/
├── config.json     # user prefs
├── playlists/*.json
└── voices/         # piper voices

~/.cache/siren/meta.json   # metadata cache
```

---

## 🎯 PRIORITY FEATURES TO IMPLEMENT

### Open (next candidates)
1. **P1-001: Tab Completion** - Easy, high impact
2. **P2-004: Color Themes** - Custom TUI schemes
3. **P3-007: Play Counts & Ratings** - sqlite3
4. **P3-008: Smart Playlists** - generated from metadata/history

### Shipped (do not re-implement)
- Queue system (P1-003) · Playlists (P1-002) · Fuzzy search (P1-004)
- Metadata caching (P1-005) · Error handling pass (P1-006)
- Volume normalization (P2-001) · Gapless (P2-002) · Config system (P2-007)
- Repeat modes (P2-003) · Progress bars (P2-005) · FFT EQ (P3-005)

---

## 📚 ESSENTIAL FILES TO READ

### 1. Main Entry Point (`bin/siren`)
- Single file; section banners: config / fuzzy / metadata / library / mpv client /
  queue+playlists / playback / waves / TUI / CLI main.
- mpv IPC contract: JSON over `/tmp/siren-mpv.sock` (idle mpv spawned with
  `--idle=yes --no-video --gapless-audio=yes --volume-max=150`).

### 2. Shared Layer (`bin/fae_termart.py`)
- `box`, `paint_frame`, `tui_begin/tui_read_key/tui_read_event/tui_cleanup`, `pad_vis`, `vis_len`.
- Mouse: `MouseEvent`, `HitMap`, `Region`, `add_list_rows`, `DoubleClickTracker`, SGR enable in `tui_begin(mouse=True)`.

### 3. Development Plan (`docs/plans/siren.md`)
- Full roadmap, technical specs, changelog.

---

## 💡 TIPS FOR SUCCESS

### 1. Start Small
- Pick one open feature; implement completely; test; document.

### 2. Test Often
```bash
python3 -m py_compile bin/siren && python3 -m pytest tests/   # 78 tests
siren play "Bury the Past"    # fuzzy smoke
siren status                  # socket/queue/mode report
```

### 3. Keep the IPC Contract
- Any change touching the socket must keep `starship-music`, `faectl`, the prompt
  tick (`shell/pixie.zsh`), and `kur_voice.py` working. Socket path:
  `/tmp/siren-mpv.sock` (override via `SIREN_SOCK`).

---

## 🆘 TROUBLESHOOTING

**Issue: mpv not found**
```bash
sudo pacman -S mpv  # Arch
```

**Issue: TUI broken/blank**
```bash
# Siren needs a real TTY; from a pipe it exits 2 with a message.
# If it hangs, ensure fae_termart is on PATH (~/bin) and PIXIE_UNICODE=1.
```

**Issue: stale socket**
```bash
pkill -x mpv; rm -f /tmp/siren-mpv.sock   # next command respawns idle mpv
```

**Issue: metadata shows filenames instead of Artist - Title**
```bash
# mutagen is optional; install it to get tagged metadata:
pip install mutagen
```

---

## 🎉 FIRST FEATURE IMPLEMENTATION

### Suggested: Tab Completion (P1-001)

**Time needed:** 1-2 hours  
**Impact:** High  
**Difficulty:** Medium

#### Steps:
1. **Read** `main()` in `bin/siren` to see the manual dispatch (no argparse).
2. **Add** a small completer for `play`/`queue add` that lists `~/Music/**/*.{mp3,flac,ogg,…}`
   (e.g. via a `complete()` helper + `readline`), or add a `siren complete` command.
3. **Test** with `siren play <TAB><TAB>`
4. **Document** in the development plan

---

*Last updated: 2026-08-05*
