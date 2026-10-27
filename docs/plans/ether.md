# Ether — network manager

**Role:** Overall network management: bluetooth, wifi, lan; `veil` VPN toggle; `bridge` phone-hotspot boot fallback; `ap` house Wi-Fi access point; `status` one-shot; `about`.

**Status:** stable

## Current
- `ether` — TUI: w/l weave, s scan (top 5), n new, d remove, R restart (soft/sudo), r refresh, q quit
- `ether status` — one-shot report (bt/wifi/lan)
- **Conjuring panel** — lists active downloads ("what the loom is conjuring"): scans partial files (`.part*`, `.tmp*`, `.incomplete`, aria2 pairs) in the model dir, `~/Downloads`, pacman cache, `/tmp`; siren-style bar + % when a `<name>.size` sidecar (total bytes) sits next to the partial group (menagerie writes these for model downloads); idle: "nothing being conjured"
- `ether net` — connectivity diagnosis (IPv4 HTTPS for archive.org etc.)
- `ether veil on|off` — VPN toggle (`vpn`)
- `ether bridge` — phone hotspot CLIENT boot fallback (nmcli); env `~/.config/ether/netherweave.env` (chmod 600, never committed); runs at boot via `ether-bridge.service`
- `ether ap on|off|status` — the house Wi-Fi AP: iw + hostapd (+ dnsmasq DHCP when present), NetworkManager-free; raises the radio from monitor to `__ap`, restores managed on off; conf/pids under `/run/user/$UID/ether/` (0600/0700)
- `whisper ether` / `listen ether` — BT audio: ANC headphone / JBL Go 3 (each sets default sink)

## House AP vs phone bridge
- **House AP** (`ether ap`): the box SERVES Wi-Fi for lanterns/speakers. Raw `iw` + `hostapd` on `wlp41s0`; NetworkManager is never started or consulted. If `hostapd` is missing, ether prints `pacman -S hostapd` and exits nonzero — never a silent no-op.
- **Phone bridge** (`ether bridge`): the box CLIENTS to a phone hotspot when no real link is up. Still nmcli; left as-is on the phone-client path.
- Credentials for the AP: `~/.config/ether/ap.env` (0600) with `ETHER_AP_IFACE` / `ETHER_AP_SSID` / `ETHER_AP_PSK`; ether falls back to `~/.config/wisp/ap.env` (`WISP_AP_*`) so the existing wisp file keeps working. The PSK is never printed — status only says `psk set`.
- Wisp talks to the AP only through `ether ap …` (same pattern as `siren heos --json` for speakers). `wisp/src/ap.rs` holds no nmcli and no ap.env reader.

## Next
- [ ] Wifi networks saved/prioritized; reconnect on boot
- [ ] LAN: show interfaces/IPs/mounts
- [ ] Bridge: wizard to write netherweave.env
- [ ] Profile "weaves" editor (named network setups)

## Notes
- `ia.py` (Internet Archive engine) moved OUT of ether — ether is networking only.
- hostapd + dnsmasq are in `pkglist.txt` (house AP path).
