# 🚀 SIREN - QUICK START GUIDE FOR DEVELOPERS

**Purpose:** Get any agent/developer productive with Siren development in 5 minutes.

---

## 📋 IMMEDIATE ACTIONS

### 1. Understand the Current State
```bash
# See what files exist
ls -la ~/bin/siren*

# Check the main entry point
head -20 ~/bin/siren

# See what music is available
ls ~/Music/siren/
```

### 2. Test Current Functionality
```bash
# Start the interactive TUI
siren

# Play some music
siren play ~/Music/siren/pkmn-rse-soundtrack/

# Try free archive
siren trove 10 music lofi   # search Internet Archive + pick
siren trove get <id>        # download one item to ~/Music/trove or ~/Videos/trove

# Check help
siren --help
```

---

## 🎯 PICK A FEATURE TO IMPLEMENT

### Quick Wins (Can do in 1 session)

#### 🔹 Feature: Tab Completion (P1-001)
**Goal:** Add tab completion for commands and file paths

```bash
# Install dependency
pip install argcomplete

# Edit siren file - add at top:
import argcomplete

# Add to main() function:
argcomplete.autocomplete(ap)

# Test: Type 'siren play ' then TAB should show suggestions
```

#### 🔹 Feature: Queue System (P1-003 — already built)
**Siren already has a queue** (added 2026-08-03) — play with it before building more:

```bash
siren queue add ~/Music/album/*.flac
siren queue list
siren queue next
siren queue clear
```

The TUI has a queue panel too (press `1` to focus it). No work needed here — pick an open feature instead (see Phase 1 below).

---

## 📁 PROJECT STRUCTURE

### Current (What You Have)
```
bin/
├── siren           # Main script (CLI + TUI + trove) - edit this
├── siren_player.py # Playback logic (mpv IPC)
└── siren_waves.py  # Visualization
```

### Target (What to Build Toward)
```
bin/
├── siren/          # Package directory
│   ├── __init__.py
│   ├── __main__.py  # CLI entry
│   ├── core/
│   │   ├── player.py
│   │   ├── library.py
│   │   └── queue.py
│   └── utils/
│       └── config.py
└── siren           # Symlink to siren/__main__.py
```

---

## 🛠️ COMMON TASKS

### Add a New Command
```python
# In siren file, add to subparsers:
sub.add_parser("mycommand", help="My new command")

# Add handler:
if cmd == "mycommand":
    return my_command_handler(args)
```

### Add Configuration
```python
# In siren file, add at top:
import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "siren" / "config.json"

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}

def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
```

### Add Error Handling
```python
# Wrap mpv calls:
try:
    # mpv command here
    pass
except subprocess.CalledProcessError as e:
    print(f"Error: {e}")
    return 1
except Exception as e:
    print(f"Unexpected error: {e}")
    return 1
```

---

## 🎯 PRIORITY FEATURES TO IMPLEMENT

### Phase 1 (Do These First)
1. **P1-001: Tab Completion** - Easy, high impact
2. **P1-006: Error Handling** - Improves reliability
3. **P1-004: Fuzzy Search** - Better UX
4. **P1-005: Metadata Caching** - Faster browsing

(Queue P1-003 and Playlists P1-002 are already shipped — see current-state checklist.)

### Phase 2 (Do These Next)
1. **P2-001: Volume Normalization** - Loudness consistency
2. **P2-007: Configuration** - User customization
3. **P2-002: Gapless Playback** - Seamless transitions

---

## 📚 ESSENTIAL FILES TO READ

### 1. Main Entry Point (`siren`)
- Understand command parsing
- See how subcommands work
- Learn the TUI structure

### 2. Player Module (`siren_player.py`)
- Core playback logic
- mpv integration
- Track management

### 3. Development Plan (`docs/plans/siren.md`)
- Full roadmap
- Technical specifications
- Implementation guidance

---

## 🚀 DEVELOPMENT CHECKLIST

### Before Starting
- [ ] Read this quick start guide
- [ ] Read the development plan
- [ ] Test current functionality
- [ ] Pick a feature to implement

### During Development
- [ ] Follow code style guidelines
- [ ] Add proper error handling
- [ ] Test each change
- [ ] Document new functionality

### Before Committing
- [ ] Update development plan status
- [ ] Add to changelog
- [ ] Test with real music files
- [ ] Clean up temporary files

---

## 💡 TIPS FOR SUCCESS

### 1. Start Small
- Pick one feature from Phase 1
- Implement it completely
- Test thoroughly
- Document it

### 2. Test Often
```bash
# Test basic playback
siren play ~/Music/siren/pkmn-rse-soundtrack/54\ -\ Slateport\ City\ \[Bonus\ Track\].flac

# Test your new feature
siren mycommand
```

### 3. Use Version Control
```bash
# If using git:
git add .
git commit -m "Add tab completion feature"
git push
```

### 4. Document Everything
- Update `docs/plans/siren.md`
- Add comments in code
- Write usage examples

---

## 🆘 TROUBLESHOOTING

### Common Issues

**Issue: mpv not found**
```bash
# Install mpv
sudo pacman -S mpv  # Arch
sudo apt install mpv  # Debian/Ubuntu
```

**Issue: Python module not found**
```bash
pip install missing-module
```

**Issue: Audio not playing**
```bash
# Test mpv directly
mpv ~/Music/siren/pkmn-rse-soundtrack/*.flac
```

**Issue: TUI not working**
```bash
# Check terminal support
python3 -c "import curses; print('curses OK')"
```

---

## 📞 GETTING HELP

### Resources
1. **This file** - Quick start guide
2. **docs/plans/siren.md** - Full roadmap
3. **Existing code** - Learn from current implementation
4. **Python docs** - For language questions
5. **mpv docs** - For playback questions

### Debug Commands
```bash
# Verbose mode
siren -v play ~/Music/siren/pkmn-rse-soundtrack/*.flac

# Check mpv version
mpv --version

# Check Python version
python3 --version
```

---

## 🎉 FIRST FEATURE IMPLEMENTATION

### Suggested: Add Tab Completion (P1-001)

**Time needed:** 1-2 hours  
**Impact:** High  
**Difficulty:** Medium

#### Steps:
1. **Read** `siren` to find the subparser setup and `main()`
2. **Add** `import argcomplete` and `argcomplete.autocomplete(ap)` before `args = ap.parse_args()`
3. **Add** a completion function for the `play` command that lists `~/Music/**/*.{mp3,flac,ogg,…}`
4. **Test** with `siren play <TAB><TAB>`
5. **Document** in the development plan

#### Code sketch:
```python
# In siren, near the top:
import argcomplete

# In main(), right before parse_args():
argcomplete.autocomplete(ap)
```

---

**Ready to start?** Pick a feature from Phase 1 and begin! The development plan has all the details you need.

*Last updated: 2026-08-03*