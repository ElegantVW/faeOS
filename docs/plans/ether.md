# Ether — network manager

**Role:** Overall network management: bluetooth, wifi, lan; `veil` VPN toggle; `bridge` phone-hotspot boot fallback; `status` one-shot; `about`.

**Status:** stable

## Current
- `ether` — TUI: w/l weave, s scan (top 5), n new, d remove, R restart (soft/sudo), r refresh, q quit
- `ether status` — one-shot report (bt/wifi/lan)
- **Conjuring panel** — lists active downloads ("what the loom is conjuring"): scans partial files (`.part*`, `.tmp*`, `.incomplete`, aria2 pairs) in the model dir, `~/Downloads`, pacman cache, `/tmp`; siren-style bar + % when a `<name>.size` sidecar (total bytes) sits next to the partial group (menagerie writes these for model downloads); idle: "nothing being conjured"
- `ether net` — connectivity diagnosis (IPv4 HTTPS for archive.org etc.)
- `ether veil on|off` — VPN toggle (`vpn`)
- `ether bridge` — hotspot boot fallback; env `~/.config/ether/netherweave.env` (chmod 600, never committed); runs at boot via `ether-bridge.service`
- `whisper ether` / `listen ether` — BT audio: ANC headphone / JBL Go 3 (each sets default sink)

## Next
- [ ] Wifi networks saved/prioritized; reconnect on boot
- [ ] LAN: show interfaces/IPs/mounts
- [ ] Bridge: wizard to write netherweave.env
- [ ] Profile "weaves" editor (named network setups)

## Notes
- `ia.py` (Internet Archive engine) moved OUT of ether — ether is networking only.
