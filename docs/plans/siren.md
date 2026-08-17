# 🎵 SIREN MEDIA PLAYER - COMPREHENSIVE DEVELOPMENT PLAN

**Version:** 2.0  
**Last Updated:** 2026-08-05  
**Status:** Active Development  
**Maintainer:** evenweaker  

---

## 📋 EXECUTIVE SUMMARY

Siren is a **fey media player** built in Python that uses `mpv` as its audio backend. It features an interactive TUI, free archive integration (Internet Archive), and music library management. As of v2.0 Siren is a **single-file app** (`bin/siren`) in the faeOS house pattern — no module split — with config persistence, fuzzy search, a metadata cache, gapless playback, and volume normalization.

---

## 🎯 CURRENT STATE ASSESSMENT

### ✅ What Works
- [x] Core media playback via mpv (JSON IPC over unix socket `/tmp/siren-mpv.sock`)
- [x] Interactive TUI with browser · queue · EQ panels (fae_termart shared layer)
- [x] Free archive integration (Internet Archive via shared `ia.py`)
- [x] Waves EQ (FFT + ffmpeg slice + tide-echo fallback)
- [x] Playback controls (play, pause/toggle, stop, next, prev, random)
- [x] Queue system (`siren queue add|list|clear|play|next|remove|move`)
- [x] Persistent playlists (JSON in `~/.config/siren/playlists/`)
- [x] Repeat modes + shuffle (`r` in EQ panel)
- [x] Fuzzy search (tiered scorer; exact/prefix/substring/tokens/subsequence)
- [x] Metadata cache (`~/.cache/siren/meta.json`, keyed by path + mtime, saved atexit)
- [x] Config persistence (`~/.config/siren/config.json`, atomic tmp+replace write)
- [x] Gapless playback (`--gapless-audio=yes` + runtime `gapless-audio` property)
- [x] Volume normalization (mpv `replaygain-mode track`, toggled by `normalize`)
- [x] Test suite (`tests/test_siren.py`, 31 tests, pure-logic, no mpv/TTY needed)

### ⚠️ Current Limitations
- [ ] Tab completion (P1-001)
- [ ] No plugin system (P3-004)
- [ ] Smart playlists / play counts / ratings (P3-007, P3-008)
- [ ] Mouse support (P2-008)

### 📊 Current File Structure
```
bin/
├── siren                    # Single-file app: CLI + TUI + engine + waves
├── fae_termart.py           # Shared TUI layer (frames, paint, tui_* helpers)
├── ia.py                    # Shared Internet Archive engine (trove)
└── ...                      # (siren_player.py / siren_waves.py removed in v2.0)

~/.config/siren/
├── config.json              # user prefs (see below)
├── playlists/*.json         # saved playlists
└── voices/                  # piper TTS voices (used by kur_voice.py)

~/.cache/siren/meta.json     # metadata cache
```

---

## 🚀 DEVELOPMENT ROADMAP

### Phase 1: Core Experience (Priority: HIGH)

| ID | Feature | Description | Status | Files to Modify | Dependencies |
|----|---------|-------------|--------|-----------------|--------------|
| P1-001 | **Tab Completion** | Add tab completion for commands and file paths | ⏳ Not Started | `siren` | `argcomplete` |
| P1-002 | **Persistent Playlists** | Save/load playlists between sessions | ✅ Done (2026-08-03) | `siren` | `json`, `pathlib` |
| P1-003 | **Queue System** | Add tracks to queue instead of immediate playback | ✅ Done (2026-08-03) | `siren` | None |
| P1-004 | **Fuzzy Search** | Tiered fuzzy matching for music queries | ✅ Done (2026-08-05) | `siren` (fuzzy_score) | None |
| P1-005 | **Metadata Caching** | Cache audio metadata for fast browsing | ✅ Done (2026-08-05) | `siren` (meta cache) | mutagen (optional) |
| P1-006 | **Improved Error Handling** | Graceful degradation and user-friendly errors | ✅ Done (2026-08-05) | `siren` | None |

#### 📋 Phase 1 Implementation Notes
- **P1-004**: `fuzzy_score` tiers — 10 exact · 9 prefix · 8 substring · 7 all tokens · 6 ordered subsequence; bonus = matched chars as tiebreak. No third-party deps.
- **P1-005**: `meta.json` keyed `path → {m, d}` where m = mtime_ns (invalidation), d = display string. Lazy `mutagen` import; filename fallback when missing.
- **P1-006**: `siren play <unmatched>` now errors instead of playing the whole library; `Player` never spawns mpv for reads; missing-file queue entries dropped by `validate()`.

---

### Phase 2: Enhanced Features (Priority: MEDIUM)

| ID | Feature | Description | Status | Files to Modify | Dependencies |
|----|---------|-------------|--------|-----------------|--------------|
| P2-001 | **Volume Normalization** | ReplayGain-track normalization between tracks | ✅ Done (2026-08-05) | `siren` (normalize cfg → `replaygain-mode track`) | mpv |
| P2-002 | **Gapless Playback** | Eliminate silence between tracks | ✅ Done (2026-08-05) | `siren` (gapless cfg → `--gapless-audio=yes`) | mpv |
| P2-003 | **Repeat Modes** | Repeat track, repeat playlist, shuffle repeat | ✅ Done (2026-08-03) | `siren` | None |
| P2-004 | **Color Themes** | Multiple color schemes for TUI (pink is the default) | ⏳ Not Started | `siren` | `fae_termart` |
| P2-005 | **Progress Bars** | Visual progress for current track | ✅ Done (2026-08-03) | `siren` | custom |
| P2-006 | **Track Info Panel** | Show metadata, album art (ASCII) | ⏳ Not Started | `siren` | `mutagen`, `Pillow` |
| P2-007 | **Configuration System** | Persistent settings (`config get|set`) | ✅ Done (2026-08-05) | `siren` (SirenConfig) | `json` |
| P2-008 | **Mouse Support** | Click/select, double-click activate, wheel, panel focus via shared `fae_termart` SGR + HitMap | ✅ Done (2026-08-16) | `fae_termart`, `siren` | stdlib CSI (no curses) |

#### 📋 Phase 2 Implementation Notes
- **P2-001/002/007**: applied at mpv spawn via `apply_runtime_prefs`; volume only set on fresh spawn so live user changes are never stomped.
- **P2-007**: keys — `default_volume` (0-150), `library_roots` (list), `fuzzy_search`, `waves`, `gapless`, `normalize`, `cache_meta`, `mouse` (bools), `wave_bands` (8/16/32). Sanitized on load; atomic write via `.tmp` + `replace`.
- **P2-008**: SGR mouse in `fae_termart` (`tui_begin(mouse=)`, `tui_read_event`, `HitMap`); siren registers browser/queue rows + panel titles; double-click activate; wheel under cursor. Queue `j/k` now moves a selection cursor (play with enter), not reorder.
- **Mid layout (2026-08-16):** browser + queue are real crystal `art.panel` frames via `split_row` / `split_widths` (same chrome as header/runes). Focus uses `focus_mark` (no ANSI slicing). Header/footer full-bleed (`cap=None`). Waves optional full-width panel.

---

### Phase 3: Advanced Features (Priority: LOW)

| ID | Feature | Description | Status | Files to Modify | Dependencies |
|----|---------|-------------|--------|-----------------|--------------|
| P3-001 | **YouTube Integration** | Search and play YouTube content | ⏳ Not Started | New module | `pytube` |
| P3-002 | **SoundCloud Support** | Access SoundCloud tracks | ⏳ Not Started | New module | API |
| P3-003 | **Spotify Connectivity** | For users with Spotify accounts | ⏳ Not Started | New module | `spotipy` |
| P3-004 | **Plugin System** | Allow users to add custom commands/features | ⏳ Not Started | `siren` | `importlib` |
| P3-005 | **Visualizations** | Advanced audio spectrum analyzers | ✅ Done* (FFT EQ in TUI) | `siren` | None (stdlib only) |
| P3-006 | **Album Art Display** | Show embedded or fetched album art | ⏳ Not Started | `siren` | `Pillow` |
| P3-007 | **Play Counts & Ratings** | Track usage and allow ratings | ⏳ Not Started | New module | `sqlite3` |
| P3-008 | **Smart Playlists** | Auto-generated playlists | ⏳ Not Started | `siren` | None |

---

### 🖇️ Spellbook Bridge (done 2026-08-05)
- **Siren TUI keys:** `f` open a file · `F` open a directory (plays every audio file inside) — both launch Spellbook as the file manager (`--pick --output`), via the same forkpty bridge pattern as tome.
- **Spellbook:** added `p` in `--pick` mode → picks the *current* directory (picker otherwise returns files only); footer hint shown in pick mode.
- Build: `pick_path_via_spellbook(fd, start_dir)` in `siren`; parent fd stays in cbreak so keystrokes pass through raw.

---

## 🔧 TECHNICAL SPECIFICATIONS

### Core Dependencies
```
Runtime (all optional except mpv + stdlib):
- Python 3.10+ (dataclasses, `int | None` unions)
- mpv (backend; spawned with --idle=yes --no-video --gapless-audio=yes
       --volume-max=150 --input-ipc-server=/tmp/siren-mpv.sock)
- fae_termart.py (shared pink TUI layer)
- mutagen (optional, lazy: metadata tags when present, filename fallback otherwise)
- ffmpeg (optional, for EQ slice; tide-echo fallback otherwise)

Planned / optional (future):
- pytube (YouTube) · spotipy (Spotify) · Pillow (album art)
- argcomplete (tab completion)
- mouse: shared `fae_termart` SGR 1006 + HitMap (not curses)
```

### Configuration File Format
```json
{
  "default_volume": 75,
  "library_roots": ["~/Music"],
  "fuzzy_search": true,
  "waves": true,
  "gapless": true,
  "normalize": false,
  "cache_meta": true,
  "wave_bands": 16
}
```

### Playlist File Format
```json
{
  "name": "favorites",
  "created": "2026-08-05T12:00:00Z",
  "modified": "2026-08-05T12:00:00Z",
  "tracks": [
    {"path": "/home/u/Music/A/01 Night Drive.flac",
     "display": "Artist - Title", "title": "Title", "artist": "Artist",
     "duration": 243.5}
  ]
}
```

### IPC & Integration Contract
- Socket: `/tmp/siren-mpv.sock` (override: `SIREN_SOCK` env).
- Consumers that MUST stay compatible: `starship-music`, `faectl` status probe, `shell/pixie.zsh` tick, `kur_voice.py` (fixed in v2.0 from stale `/tmp/mpv-music.sock`).
- Env overrides for testing: `SIREN_CONFIG_DIR`, `SIREN_CACHE_DIR`, `SIREN_SOCK`.

---

## 🛠️ DEVELOPMENT WORKFLOW

1. **Edit `bin/siren`** — single file; keep the section banner structure (config / fuzzy / metadata / library / mpv client / queue+playlists / playback / waves / TUI / CLI main).
2. **Run tests**
   ```bash
   python3 -m pytest tests/          # 78 tests (47 fae_termart + 31 siren)
   python3 -m py_compile bin/siren   # syntax gate
   ```
3. **Smoke** `siren about` · `siren config get|set` · `siren play <query>` · TUI under a PTY.
4. **Update docs** — this plan, `SIREN_QUICK_START.md`, `faeOSplan.md` log.

### Code Style Guidelines
- faeOS house pattern: `from __future__ import annotations`-style unions, `fae_termart as art`, `Palette as P`, `os.environ["PIXIE_UNICODE"] = "1"`, `NAME` constant, `main(argv) -> int` entry.
- Type hints everywhere; small functions; no comments unless asked; `try/except OSError` for all IO.
- New logic must come with a pytest case in `tests/test_siren.py` (import via `SourceFileLoader` since `bin/siren` is extensionless).

---

## 📊 QUALITY ASSURANCE

### Test Coverage (tests/test_siren.py)
| Area | Cases |
|------|-------|
| Config | defaults, save/load round-trip, sanitization, `cli_set_config` |
| Fuzzy | tier matrix, exact-beats-prefix, ranked ordering, empty-query |
| Metadata | filename fallback, cache persist, stale invalidation, unknown path |
| Queue | add/remove/clear/move, validate drops missing, metadata snapshot |
| Playlists | save/load/list/delete JSON, delete missing |
| Resolution | existing file, fuzzy query, unmatched → empty, extension filter |
| mpv client | dead-socket behavior (never spawns on read) |
| Misc | `fmt_clock`, `AUDIO_EXT` |

---

## 📝 CHANGELOG

### Version 2.0 (2026-08-05) — Full rewrite, single-file house pattern
- Consolidated `siren_player.py` + `siren_waves.py` into `bin/siren` (2179 ln); old modules deleted.
- Config persistence: `SirenConfig` dataclass, `~/.config/siren/config.json`, `siren config get|set` (P2-007).
- Fuzzy search: tiered scorer, `resolve_library` ranking, `fuzzy_search` toggle (P1-004).
- Metadata cache: `meta.json` keyed path+mtime, atexit save, lazy mutagen (P1-005).
- Gapless (`gapless`) + ReplayGain normalization (`normalize`) applied at spawn (P2-001/002).
- `siren play <unmatched>` errors instead of silently playing the whole library (P1-006).
- Fixed socket path inconsistency: `kur_voice.py` now uses `SIREN_SOCK`/`/tmp/siren-mpv.sock`.
- `resolve_play_args` fast-path for direct existing file paths.
- Tests: `tests/test_siren.py` added (31 tests); full suite 78 passing.

### Version 1.1 (2026-08-03)
- Queue system shipped (P1-003); playlists shipped (P1-002); shuffle+repeat (P2-003); progress bar (P2-005).
- TUI migrated to shared `fae_termart` layer; screen holds via `pixie-screen`.

### Version 1.0 (2026-08-01)
- Initial development plan created; roadmap defined through Phase 3.

---

## 🔮 FUTURE VISION

### Long-term Goals (6-12 months)
1. **Fully plug-and-play** — install once, everything works: shared TUI layer, screen policy, config persistence.
2. **Best-in-class offline player** — smart playlists, play counts/ratings, album art, local + free-archive library.
3. **Deep FaeOS integration** — prompt tick, scry, pixie-screen holds, `scroll` help, spellbook browsing of the library.

### Ultimate Vision
Siren becomes the **premier offline-first terminal media player**, with:
- Seamless local + free-archive (Internet Archive) library
- Beautiful, functional terminal interface (pink, consistent with the ecosystem)
- Zero telemetry, zero accounts, zero cloud
- Deep integration with the rest of FaeOS (prompt, tick, scry)

### Anti-goals
- Cloud sync, streaming-service accounts (Spotify/SoundCloud as primary), mobile apps, GUI-first — these contradict the FaeOS privacy/offline-first objective and are deliberately out of scope.

---

**Next Steps:**
- [ ] P1-001 Tab Completion
- [ ] P2-004 Color Themes
- [ ] P3-007 Play Counts & Ratings
- [ ] P3-008 Smart Playlists

---

*This development plan is a living document. Update it as progress is made and priorities change.*

**Maintained by:** evenweaker  
**Contributions welcome!** 🚀
