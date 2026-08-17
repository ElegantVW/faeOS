# Bulwark — host ward

**Role:** Network wall (Aegis), integrity photo (Purity), open windows (Sentinel), hunt (Ward).  
**Status:** honest MVP in progress — default-deny desktop, posture that cannot flatter  
**Repo:** [ElegantVW/bulwark](https://github.com/ElegantVW/bulwark) → `~/bulwark`  
**Not Seal:** Seal seals the glass (lock/greeter). Bulwark watches the house.

## Plug in

```bash
git clone git@github.com:ElegantVW/bulwark.git ~/bulwark
cd ~/bulwark && ./build.sh install
# wall is still down until:
sudo bulwark aegis apply desktop && bulwark aegis confirm
bulwark   # look
```

Contract: [docs/engines.md](../engines.md). Voice: [docs/cli-voice.md](../cli-voice.md).

## Profiles

| Profile | Intent |
|---------|--------|
| `desktop` | Personal default: deny inbound, no SSH, fae ports 127.0.0.1 only |
| `strict` | Tight inbound |
| `server-ssh` | Like server — allows TCP 22 |

## Human forms

| Human | Machine |
|-------|---------|
| bare `bulwark` | TUI truth ritual |
| activate bulwark | dirs + posture; invite Raise Aegis if wall down |
| Aegis protect / Raise Aegis | `aegis apply desktop` + confirm |
| Aegis release | `aegis undo` |
| Ward report | `ward` |
| Purity photo | `purity baseline` |

## Success bar (faeOS)

- Desktop policy does not open SSH  
- Missing / unknown Aegis ⇒ never SAFE  
- AI ports must not face the LAN while mood says SAFE  
- Reboot persistence = later phase (system restore unit)  
