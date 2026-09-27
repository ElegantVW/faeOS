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

## hud-2026-09-27
- NEW bin/fae-hud: themed X11 window-cycler panel in C. Xlib + Xft only, no
  other runtime deps. Viewer only: never focuses, kills, moves or resizes.
  Spawned per Alt+Tab by fae-cycle; paints, holds, fades, exits. No resident
  process (the i3bar lesson). Reads EWMH only, so it is WM-agnostic.
  `fae-hud --dump` prints the raw window list, because the first question
  about a window list is "is the data there", not "does it look right".
- fae-cycle: spawn fae-hud with the window it just focused. The HUD paints
  BEFORE the kitty toast, so a cue exists even when the target is not kitty.
- BUGFIX (fae-cycle, latent): `set -euo pipefail` plus any pipeline where one
  stage fails aborted the script with no message and rc=1, after focus had
  already moved. Two triggers, both hit in normal use:
    * `kitty @ send-key ... && toasted=1` — the `&&` list fails when the target
      is not kitty (no @faeos-kitty-<pid> socket), so `set -e` exited.
    * `kid=$(kitty @ ... ls | python3 ...)`, `name=$(xprop ... | cut)`,
      `con=$(tree | python3 ...)`, `state=$(...)` — pipefail propagates a
      non-zero from any stage.
  Every pipeline assignment is now guarded. Symptom before the fix: Alt+Tab
  moved focus and then silently did nothing, and stderr was invisible anyway
  because i3's fd 2 is /dev/tty1. Verified: 67/67 invocations succeed, in
  both directions, including while windows are created and destroyed.
- BUGFIX (i3 config): Super+drag was broken because this file had been
  slimmed from the 2026-09-23 backup and dropped `tiling_drag modifier`,
  `floating_modifier $mod` and `for_window [class=".*"] floating enable`.
  Those three are the whole reason Super+drag works. Rebuilt the config from
  the Sep 23 baseline (198 lines) and restored them. Also: an explicit
  `bindsym $mod+button1 ... drag move` SHADOWS tiling_drag, which is what
  made the breakage look like "i3 ignores my drag".
  Measured: floating_modifier + drag on a floating window moves it exactly
  the dragged distance; the `drag` *command* produces 0px on this machine.
