# Wizard's Tower (faectl) — control panel

**Role:** FaeOS control panel & service supervisor. The face of the system: status dashboard, service control, first-run wizard.

**Status:** stable (minimal: `status`, `restart-llm`)

## Current
- `faectl status` — dashboard: LLM (8080), Kur (8081), Siren, audio, services
- `faectl restart-llm` — restart the local LLM

## Next
- [ ] Rename/brand to Wizard's Tower (keep `faectl` as the command for now)
- [ ] Per-service start/stop/restart (goblin, kur, ether-bridge, siren)
- [ ] First-run wizard (Phase 2): user name, music dir, mail account, hotspot env, model download
- [ ] Upgrade check + diagnostics (`faectl doctor`): log tailing, disk, unit status
- [ ] Distro phase: becomes the post-install landing app

## Notes
- Uses shared `pixie_termart` frames; should adopt `tui_*` layer when it grows a TUI.
