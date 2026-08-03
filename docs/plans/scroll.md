# Scroll — help menu

**Role:** Themed command directory / interactive help picker. Every app (except easter eggs) has a section here. New-user discovery.

**Status:** stable

## Current
- `scroll` — TUI arrow picker → prints selection to prompt (`print -z` in zsh)
- `scroll list` / `scroll menu` — static boxed board / raw lines
- Sections: ETHER, SIREN, AI (pixie/faectl), MAIL, misc (spellbook, faectl, zen, tick…)
- Runs on shared `tui_*` layer; fzf path with screen hold

## Next
- [ ] Keep SECTIONS in sync with every app change (rule: app plan update ⇒ scroll section update)
- [ ] Grouped navigation (jump to section by key)
- [ ] Per-app detail pages (deep help) instead of flat blurbs
- [ ] Kur stays hidden (easter egg)

## Notes
- Kur is deliberately NOT listed (easter egg).
