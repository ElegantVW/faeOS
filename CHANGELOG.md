# faeOS changelog

## housekeeping (2026-09-26)

- Kur splits to `ElegantVW/kur` (client + voice daemon + redacted quest).
  Hatch help now names both daemons (`:8083` pen vs `:8081` mind).
- Scroll gains Mourama + Grove pages; Seal/Pixie pages note their repos;
  curriculum grows two slots. Installed book refreshed via `install.sh`.
- New `tv` command: persistent CRT shader toggle (`on/off/status`).
- Content pipeline: `shots.yaml` recipes, `sequence` runner, `sigil2svg`,
  `sigil2story`, `story2clip`, `storyify` + batch log.
- Tests: pytest absent on this box (unittest only) — recorded gap.

## seal-moved (2026-09-26)

- Seal source leaves `faeOS/seal/` for `ElegantVW/bulwark` `glass/`.
  faeOS keeps thin launchers; `docs/engines.md` + `install.sh` updated.
- Pixie canonical repo: `ElegantVW/pixie`. Hearth/rift marked incomplete.
- Goblin `steal` naming; magpie TUI-browser surface.

## keys-2026-09-27
- Super+Return/Shift+Return/Ctrl+Shift+Return open kitty (nothing was bound).
- Super+drag move/resize via --whole-window (verified: xdotool drag moved a
  test window 12,12 -> 12,49 and flipped it floating).
- fae-cycle cue: plain-ascii toast, targeted pid -> socket -> kitty-window-id.

## cues-2026-09-27
- fae-cycle: added an audit log ($XDG_RUNTIME_DIR/fae-cycle.log). i3 runs
  `exec` with stderr inherited from i3, and i3's fd 2 is /dev/tty1 — so the
  stderr cue has been invisible since it was written. The log is how we tell
  "binding never fired" from "fired and you could not see it".
- fae-cycle: new visible cue — kitty `set-tab-color` tints the tab bar of the
  window you land in, reverted after 0.9s by a short-lived background sleep
  (no resident process). This build has no `set-tint`.
- i3: mouse_warping output -> none (matches the comment's stated intent).
- Diagnosis: i3's `drag` is inert on this machine. The press reaches i3 and
  `floating enable` runs (floating goes auto_off -> user_on), but `drag move`
  and `drag resize` both produce exactly 0px of movement. Tried: bare drag,
  floating-enable chain, explicit `drag button1 move`, with and without
  --whole-window, from the border and the window body, mouse_warping output
  and none, picom running and killed. Config is clean; cause unknown.
- Also: XTEST synthetic KEY events do not reach i3 in this environment (even
  a bare F9). XTEST mouse events do. So keyboard bindings cannot be verified
  by injection and need a real keypress.
