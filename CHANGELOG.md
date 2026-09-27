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

## hud-crystal-2026-09-27
- fae-hud rebuilt on cairo + pangocairo. Xft cannot round a corner — it has
  no arc primitive, only Rect/String/Glyphs — so the panel had been a hard
  rectangle and any softness was picom's shadow, not our drawing. Cairo also
  gives genuine per-pixel alpha, which plain X11 cannot do on its own.
  README amended: the old "no runtime deps beyond X11" claim is no longer
  true, and it says so rather than letting it quietly become false.
- Shape: rows are now two lines (title, then `workspace · app class`), so the
  panel spends height instead of width — 470..560 wide by ~235 tall for three
  windows, against 1220x120 before. Content-driven width with a 470 floor so
  short titles are not stubby, capped at min(560, 34% of screen). Past 14 rows
  it says `+N more` instead of outgrowing the screen.
- Crystal: 14px round corners, four drawn corner diamonds, a hairline under
  the header and above the footer, a hairline splitting the glyph column from
  the text, and a soft pink glow (concentric strokes, not a cairo shadow, so it
  survives without a compositor). Glyphs are U+25C8/U+25C7/U+00B7, all verified
  present in DejaVu Sans Mono; the hexagons U+2B21/2B22 are NOT, which is why
  the vocabulary is diamonds. All in THEME_GLYPH_* in theme.h.
- Motion: panel blooms from a 14px inset (no window resize, so no flicker),
  rows cascade 22ms apart, the focused band wipes in from the left, hold, fade.
  ~1.65s for two windows.
- Translucent via an ARGB32 visual when a compositor is present, detected by
  looking for an owned _NET_WM_CM_S* selection. Plain X11 has no per-window
  alpha, so with no compositor it falls back to a solid fill rather than
  black holes. FAE_HUD_VERBOSE=1 reports the choice; --opaque forces the
  fallback so it can be tested without stopping picom.
- BUGFIX (hud): the header, footer and corner facets rode the global fade
  envelope while the rows had their own stagger, so at ~80ms you got a
  fully-lit footer sitting under an empty body. They now join the cascade.
  Only visible by capturing frames across the timeline, not one screenshot.
- BUGFIX (hud): the focused band was drawn row_h tall, and row_h includes the
  gap *under* a row, so it reached up over the title into the header rule.
  It now hugs the row's two lines.
- HUD now sets WM_NAME as well as _NET_WM_NAME; with only the latter the
  window is invisible to `xdotool search` and `wmctrl`.
- BUGFIX (fae-cycle): a client that exits between reading _NET_CLIENT_LIST and
  scraping the tree left us holding an X id with no container, and the script
  exited 1 having done nothing. Now resolve_con/pick_target are functions and a
  dead target is retried, with the dead ids remembered — re-reading the list
  alone was not enough, because _NET_CLIENT_LIST keeps listing a window for a
  moment after its client exits, so the retry re-picked the same corpse (5
  failures in 30 under churn; now 0 in 40 each way under the same churn).
