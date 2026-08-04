# 🎵 SIREN MEDIA PLAYER - COMPREHENSIVE DEVELOPMENT PLAN

**Version:** 1.1  
**Last Updated:** 2026-08-03  
**Status:** Active Development  
**Maintainer:** evenweaker  

---

## 📋 EXECUTIVE SUMMARY

Siren is a **fey media player** built in Python that uses `mpv` as its audio backend. It features an interactive TUI, free archive integration (Internet Archive), and music library management. This document provides a complete roadmap for any agent or developer to continue Siren's development.

---

## 🎯 CURRENT STATE ASSESSMENT

### ✅ What Works
- [x] Core media playback via mpv
- [x] Interactive TUI with basic navigation
- [x] Free archive integration (Internet Archive)
- [x] Waves EQ (ASCII equalizer)
- [x] Basic playback controls (next, prev, stop, pause)
- [x] Music library organization
- [x] Search functionality

### ⚠️ Current Limitations
- [x] ~~No persistent playlists~~ — `siren playlist save|load|list|remove` (2026-08-03)
- [x] ~~No queue system~~ — `siren queue add|list|clear|play|next` + TUI queue panel (2026-08-03)
- [ ] Basic search (no fuzzy matching)
- [ ] No metadata caching
- [ ] Limited error handling
- [ ] No configuration persistence
- [ ] No tab completion
- [ ] No volume normalization

### 📊 Current File Structure
```
bin/
├── siren                    # Main entry point + TUI + trove (Internet Archive)
├── siren_player.py          # Playback engine (mpv IPC)
└── siren_waves.py           # Audio visualization

~/Music/                    # Music library (recursive)
~/Music/trove / ~/Videos/trove   # trove downloads
```

---

## 🚀 DEVELOPMENT ROADMAP

### Phase 1: Core Experience (Priority: HIGH | Effort: 2-4 weeks)

#### 🎯 Objective: Improve fundamental user experience

| ID | Feature | Description | Status | Files to Modify | Dependencies |
|----|---------|-------------|--------|-----------------|--------------|
| P1-001 | **Tab Completion** | Add tab completion for commands and file paths | ⏳ Not Started | `siren` | `argcomplete` |
| P1-002 | **Persistent Playlists** | Save/load playlists between sessions | ✅ Done (2026-08-03) | `siren`, `siren_player.py` | `json`, `pathlib` |
| P1-003 | **Queue System** | Add tracks to queue instead of immediate playback | ✅ Done (2026-08-03) | `siren_player.py` | None |
| P1-004 | **Fuzzy Search** | Implement fuzzy matching for music queries | ⏳ Not Started | `siren` | `fuzzywuzzy`, `python-Levenshtein` |
| P1-005 | **Metadata Caching** | Cache audio file metadata for faster browsing | ⏳ Not Started | `siren_player.py` | `mutagen`, `eyed3` |
| P1-006 | **Improved Error Handling** | Graceful degradation and user-friendly errors | ⏳ Not Started | All files | None |

#### 📋 Phase 1 Implementation Notes
- **P1-001**: Use `argcomplete` library for command completion
- **P1-002**: Store playlists as JSON files in `~/.config/siren/playlists/`
- **P1-003**: Add `Queue` class to `siren_player.py` with add/remove/clear methods
- **P1-004**: Use `fuzzywuzzy` for fuzzy string matching on track names
- **P1-005**: Cache metadata in SQLite database or JSON files
- **P1-006**: Wrap mpv calls in try-catch, provide fallback behavior

---

### Phase 2: Enhanced Features (Priority: MEDIUM | Effort: 4-6 weeks)

#### 🎯 Objective: Add professional-grade features

| ID | Feature | Description | Status | Files to Modify | Dependencies |
|----|---------|-------------|--------|-----------------|--------------|
| P2-001 | **Volume Normalization** | Auto-adjust volume levels between tracks | ⏳ Not Started | `siren_player.py` | `pydub`, `ffmpeg` |
| P2-002 | **Gapless Playback** | Eliminate silence between tracks | ⏳ Not Started | `siren_player.py` | `mpv` flags |
| P2-003 | **Repeat Modes** | Repeat track, repeat playlist, shuffle repeat | ✅ Done (2026-08-03) | `siren_player.py` | None |
| P2-004 | **Color Themes** | Multiple color schemes for TUI (pink is the default) | ⏳ Not Started | `siren` | `fae_termart` |
| P2-005 | **Progress Bars** | Visual progress for current track | ✅ Done (2026-08-03) | `siren` | `tqdm` or custom |
| P2-006 | **Track Info Panel** | Show metadata, album art (ASCII) | ⏳ Not Started | `siren` | `mutagen`, `Pillow` |
| P2-007 | **Configuration System** | Persistent settings and preferences | ⏳ Not Started | New: `siren_config.py` | `json`, `toml` |
| P2-008 | **Mouse Support** | Basic mouse navigation in TUI | ⏳ Not Started | `siren` | `curses` or `urwid` |

#### 📋 Phase 2 Implementation Notes
- **P2-001**: Use ReplayGain or EBU R128 loudness normalization
- **P2-002**: Use mpv's `--gapless-audio` flag
- **P2-003**: Add `repeat` enum: OFF, TRACK, ALL, SHUFFLE
- **P2-004**: Define color themes in JSON format, allow user selection
- **P2-005**: Use progress bar library or implement custom ASCII progress
- **P2-006**: Extract metadata from audio files, display in panel
- **P2-007**: Create `~/.config/siren/config.json` for settings
- **P2-008**: Use `curses` mouse events or `urwid` for mouse support

---

### Phase 3: Advanced Features (Priority: LOW | Effort: 6-8 weeks)

#### 🎯 Objective: Add cutting-edge functionality

| ID | Feature | Description | Status | Files to Modify | Dependencies |
|----|---------|-------------|--------|-----------------|--------------|
| P3-001 | **YouTube Integration** | Search and play YouTube content | ⏳ Not Started | New: `siren_youtube.py` | `pytube`, `youtube-dl` |
| P3-002 | **SoundCloud Support** | Access SoundCloud tracks | ⏳ Not Started | New: `siren_soundcloud.py` | `soundcloud` API |
| P3-003 | **Spotify Connectivity** | For users with Spotify accounts | ⏳ Not Started | New: `siren_spotify.py` | `spotipy` |
| P3-004 | **Plugin System** | Allow users to add custom commands/features | ⏳ Not Started | New: `siren_plugin.py` | `importlib` |
| P3-005 | **Visualizations** | Audio spectrum analyzers | ⏳ Not Started | `siren_waves.py` | `numpy`, `matplotlib` |
| P3-006 | **Album Art Display** | Show embedded or fetched album art | ⏳ Not Started | `siren` | `Pillow`, `requests` |
| P3-007 | **Play Counts & Ratings** | Track usage and allow ratings | ⏳ Not Started | New: `siren_library.py` | `sqlite3` |
| P3-008 | **Smart Playlists** | Auto-generated playlists | ⏳ Not Started | `siren_player.py` | None |

#### 📋 Phase 3 Implementation Notes
- **P3-001**: Use `pytube` for YouTube video extraction, play audio-only
- **P3-002**: Use SoundCloud API or unofficial libraries
- **P3-003**: Use `spotipy` for Spotify integration (requires user auth)
- **P3-004**: Create plugin interface with `setup.py` entry points
- **P3-005**: Use FFT for real-time audio visualization
- **P3-006**: Extract embedded images or fetch from online databases
- **P3-007**: Use SQLite for play counts, ratings, last played dates
- **P3-008**: Generate playlists based on metadata, play history, ratings

---

## 📁 PROJECT STRUCTURE REORGANIZATION

### Current Structure Issues
- Single-file scripts rather than a package (fine for now, module split proposed below)
- No dedicated config directory
- No proper module organization

### Proposed New Structure
```
~/.config/siren/
├── config.json              # User preferences
├── playlists/               # Saved playlists
│   └── favorites.json
├── cache/                   # Cached metadata
│   └── metadata.db
└── plugins/                 # User plugins

~/bin/
├── siren                    # Main entry point (symlink)
├── siren/
│   ├── __init__.py
│   ├── __main__.py          # CLI entry point
│   ├── core/
│   │   ├── player.py        # Playback engine
│   │   ├── library.py       # Library management
│   │   ├── archive.py       # Free archive integration
│   │   ├── waves.py         # Audio visualization
│   │   └── queue.py         # Queue system
│   ├── ui/
│   │   ├── tui.py           # Terminal UI
│   │   ├── themes.py        # Color themes
│   │   └── progress.py      # Progress bars
│   ├── utils/
│   │   ├── fuzzy.py         # Fuzzy search
│   │   ├── config.py        # Configuration
│   │   └── logging.py       # Logging
│   └── integrations/
│       ├── youtube.py      # YouTube support
│       ├── soundcloud.py    # SoundCloud support
│       └── spotify.py       # Spotify support
└── tests/                   # Test suite
```

---

## 🔧 TECHNICAL SPECIFICATIONS

### Core Dependencies
```
Actual runtime (no pip deps today):
- Python 3.8+
- mpv (media player backend, IPC socket at /tmp/siren-mpv.sock)
- fae_termart.py (shared pink TUI layer: frames, paint, tui_* helpers)

Planned / optional (future features):
- mutagen (audio metadata)          - fuzzywuzzy (fuzzy search)
- python-Levenshtein (fuzzy accel)  - requests (HTTP)
- pytube (YouTube integration)      - spotipy (Spotify integration)
- Pillow (image processing)         - numpy (audio visualization)
- argcomplete (tab completion)      - curses/urwid (advanced TUI)
```

### Configuration File Format
```json
{
  "version": "1.0",
  "theme": "default",
  "default_volume": 75,
  "normalize_volume": true,
  "gapless_playback": true,
  "repeat_mode": "off",
  "show_progress": true,
  "library_paths": [
    "~/Music/siren",
    "~/Music"
  ],
  "archive_cache": true,
  "fuzzy_search": true
}
```

### Playlist File Format
```json
{
  "name": "My Favorites",
  "created": "2026-08-01T19:00:00Z",
  "modified": "2026-08-01T19:00:00Z",
  "tracks": [
    {
      "path": "~/Music/siren/Mam168-Va-MineAllMineRecordsIv/04WildDogsInWinter-Em-i-nor.ogg",
      "title": "Wild Dogs In Winter",
      "artist": "Em-i-nor",
      "album": "Mine All Mine Records Iv",
      "duration": 243.5,
      "added": "2026-08-01T18:30:00Z"
    }
  ]
}
```

---

## 🛠️ DEVELOPMENT WORKFLOW

### For New Contributors

1. **Fork the Repository** (if applicable)
2. **Set up Development Environment**
   ```bash
   # Clone or copy existing files
   mkdir -p ~/.config/siren
   cp ~/bin/siren* ~/projects/siren/
   
   # Install dependencies
   pip install mpv mutagen requests fuzzywuzzy python-Levenshtein
   
   # Create symlink for easy testing
   ln -sf ~/projects/siren/siren ~/bin/siren-dev
   ```

3. **Run Tests**
   ```bash
   # Basic functionality test
   python3 -m siren --version
   
   # Play a test file
   python3 -m siren play ~/Music/siren/pkmn-rse-soundtrack/*.flac
   ```

4. **Submit Changes**
   - Follow existing code style
   - Add documentation for new features
   - Include tests for new functionality
   - Update this development plan

### Code Style Guidelines

```python
# Good practices:
- Use type hints (Python 3.8+)
- Follow PEP 8 style guide
- Use descriptive variable names
- Add docstrings to functions
- Keep functions under 50 lines
- Use logging instead of print()
- Handle exceptions gracefully

# Example function:
def play_track(path: str, volume: int = 75) -> bool:
    """Play a single audio track.
    
    Args:
        path: Path to audio file
        volume: Playback volume (0-100)
        
    Returns:
        bool: True if playback started successfully
    """
    try:
        # Implementation here
        return True
    except Exception as e:
        logger.error(f"Failed to play {path}: {e}")
        return False
```

---

## 📊 QUALITY ASSURANCE

### Testing Strategy

1. **Unit Tests** - Test individual functions
2. **Integration Tests** - Test component interactions
3. **End-to-End Tests** - Test complete user workflows
4. **Manual Testing** - User acceptance testing

### Test Cases to Implement

| Test ID | Description | Priority |
|---------|-------------|----------|
| T-001 | Basic playback functionality | HIGH |
| T-002 | Playlist creation and playback | HIGH |
| T-003 | Search functionality | HIGH |
| T-004 | Free archive integration | MEDIUM |
| T-005 | Error handling (missing files) | HIGH |
| T-006 | Configuration persistence | MEDIUM |
| T-007 | Queue system | MEDIUM |
| T-008 | Fuzzy search | LOW |

---

## 📚 DOCUMENTATION REQUIREMENTS

### For Each New Feature
1. **User Documentation** - How to use the feature
2. **Technical Documentation** - How it works internally
3. **Examples** - Practical usage examples
4. **Limitations** - Known issues or constraints

### Documentation Files to Maintain
- `README.md` - User guide and installation
- `CHANGELOG.md` - Version history and changes
- `CONTRIBUTING.md` - Development guidelines
- `API.md` - For plugin developers
- This file: `SIREN_DEVELOPMENT_PLAN.md`

---

## 🎯 PRIORITY MATRIX

### Immediate (Next 2 weeks)
- [ ] P1-001: Tab Completion
- [x] P1-002: Persistent Playlists — done 2026-08-03
- [x] P1-003: Queue System — done 2026-08-03
- [ ] P1-006: Improved Error Handling

### Short-term (Next 4 weeks)
- [ ] P1-004: Fuzzy Search
- [ ] P1-005: Metadata Caching
- [ ] P2-001: Volume Normalization
- [x] P2-003: Repeat Modes — done 2026-08-03

### Medium-term (Next 8 weeks)
- [ ] P2-002: Gapless Playback
- [x] P2-004: Color Themes — done 2026-08-03 (pink default; selectable themes still open)
- [x] P2-005: Progress Bars — done 2026-08-03
- [ ] P2-007: Configuration System

### Long-term (Future)
- [ ] P3-001: YouTube Integration
- [ ] P3-004: Plugin System
- [ ] P3-005: Visualizations
- [ ] P3-006: Album Art Display

---

## 🚨 KNOWN ISSUES & TECHNICAL DEBT

| Issue | Description | Priority | Status |
|-------|-------------|----------|--------|
| ISSUE-001 | Duplicate code between bin/ and pixie-kit/bin/ | HIGH | ✅ Resolved — no duplicate tree; single `bin/` |
| ISSUE-002 | No proper error handling for mpv failures | HIGH | ⏳ Not Started |
| ISSUE-003 | Memory leaks with long playback sessions | MEDIUM | ⏳ Not Started |
| ISSUE-004 | No cleanup of temporary files | LOW | ⏳ Not Started |
| ISSUE-005 | Hardcoded paths in some places | MEDIUM | ⏳ Not Started |

---

## 📞 COMMUNITY & SUPPORT

### Getting Help
- Check this development plan for current status
- Review existing code for patterns
- Test changes thoroughly before committing

### Contributing Back
- Document all changes in CHANGELOG.md
- Update this development plan with progress
- Maintain backward compatibility where possible
- Write tests for new functionality

---

## 🎉 SUCCESS METRICS

### Phase 1 Completion
- [ ] All P1 features implemented
- [ ] Basic test coverage (>80%)
- [ ] Documentation updated
- [ ] No critical bugs

### Phase 2 Completion
- [ ] All P2 features implemented
- [ ] Comprehensive test coverage (>90%)
- [ ] User documentation complete
- [ ] Performance benchmarks met

### Phase 3 Completion
- [ ] All P3 features implemented
- [ ] Plugin system documented
- [ ] Integration tests passing
- [ ] Community plugins available

---

## 📝 CHANGELOG

### Version 1.1 (2026-08-03)
- Queue system shipped: `siren queue add|list|clear|play|next` + TUI queue panel (P1-003)
- Playlists shipped: `siren playlist save|load|list|remove` (P1-002)
- Shuffle + repeat modes shipped (P2-003); progress bar + vol in header (P2-005)
- TUI migrated to shared `fae_termart` layer (`tui_begin`/`tui_read_key`/`tui_cleanup`), screen holds via `pixie-screen`
- File structure + dependencies corrected (no `siren_free.py`; runtime deps = stdlib + mpv + fae_termart)
- Vision aligned with FaeOS objective: offline-first, privacy; cloud/mobile/GUI marked anti-goals

### Version 1.0 (2026-08-01)
- Initial development plan created
- Current state assessed
- Roadmap defined through Phase 3
- Project structure proposed

---

## 🔮 FUTURE VISION

### Long-term Goals (6-12 months)
1. **Fully plug-and-play** — install once, everything works: shared TUI layer, screen policy, config persistence.
2. **Best-in-class offline player** — fuzzy search, metadata cache, smart playlists, local + free-archive library.
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

## 📌 QUICK START FOR NEW DEVELOPERS

1. **Read this entire document**
2. **Pick a feature from Phase 1** (highest priority)
3. **Fork/create a development branch**
4. **Implement the feature** following code guidelines
5. **Test thoroughly**
6. **Document the changes**
7. **Update this development plan** with progress
8. **Submit for review**

---

**Next Steps:**
- [ ] Review and prioritize Phase 1 features
- [ ] Set up development environment
- [ ] Create initial test suite
- [ ] Begin implementation of P1-001 (Tab Completion)

---

*This development plan is a living document. Update it as progress is made and priorities change.*

**Maintained by:** evenweaker  
**Contributions welcome!** 🚀