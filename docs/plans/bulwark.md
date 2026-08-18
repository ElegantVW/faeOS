# Bulwark — host ward

**Role:** Network wall (Aegis), integrity photo (Purity), open windows (Sentinel), hunt (Ward).  
**Status:** honest MVP + boot restore; entering **trust + adversarial** phase  
**Repo:** [ElegantVW/bulwark](https://github.com/ElegantVW/bulwark) → `~/bulwark`  
**Not Seal:** Seal seals the glass (lock/greeter). Bulwark watches the house.

## North star (for agents)

Path **D**: long-term cold security-review bar; mass faeOS default later.  
**Next work (ordered):** (1) Bulwark must not *be* the attacker → (2) sandbox adversarial cards → (3) only then more capability.  
Canonical: repo `AGENTS.md`, `docs/TRUST.md`, `docs/ADVERSARIAL.md`.

## Plug in

```bash
git clone git@github.com:ElegantVW/bulwark.git ~/bulwark
cd ~/bulwark && ./build.sh install
bulwark aegis apply desktop    # password via sudo
bulwark aegis confirm
bulwark install --system       # reboot restore
bulwark
```

Contract: [docs/engines.md](../engines.md). Voice: [docs/cli-voice.md](../cli-voice.md), [docs/error-voice.md](../error-voice.md).

## Profiles

| Profile | Intent |
|---------|--------|
| `desktop` | Personal default: deny inbound, no SSH, fae ports 127.0.0.1 only |
| `strict` | Tight inbound |
| `server-ssh` | Allows TCP 22 |

## Human forms

| Human | Machine |
|-------|---------|
| bare `bulwark` | TUI truth ritual |
| Raise Aegis / Aegis protect | `aegis apply desktop` + confirm |
| Release Aegis | `aegis undo` |
| Ward report | `ward` |
| Purity photo | `purity baseline` |

## Success bar (current)

- Desktop policy does not open SSH  
- Missing / unknown Aegis ⇒ never SAFE  
- AI / fae doors on LAN ⇒ DANGER  
- Reboot restore via `bulwark-aegis.service`  
- Elevate via sudo; state under SUDO_USER  

## Next bar (trust → adversarial)

- Tier 0 TRUST cards PASS on a VM  
- Tier 1 LAN peer cards PASS with commit SHAs recorded  
- No README language that implies professional sign-off until then  
