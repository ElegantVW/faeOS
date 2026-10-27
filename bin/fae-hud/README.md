# fae-hud

The house window switcher: a minimal EWMH panel that lists every open window
on the current workspace and shows which one has focus. No icons, no
window-manager coupling, no daemon.

Built because Alt+Tab worked but told you nothing. You would move focus and
have to guess whether it landed. This is the missing cue.

## Build

    make
    make install      # -> ~/bin/fae-hud
    make clean

| library    | why                                              |
|------------|--------------------------------------------------|
| Xlib       | the window, its properties, the event loop       |
| cairo      | round corners and per-pixel alpha need it        |
| pangocairo | shaped, ellipsised text                          |

## Use

    fae-hud                  # highlight _NET_ACTIVE_WINDOW
    fae-hud --cycle          # the Alt+Tab gesture: open, browse, commit once
    fae-hud --dump           # print the window list, draw nothing
    fae-hud --opaque         # the no-compositor fallback, on purpose
    fae-hud --all-workspaces # include other workspaces (default: current only)
    fae-hud --display=:N

i3 binds `Mod1+Tab` to `~/bin/fae-hud --cycle`.

While the panel is up: `Tab` steps forward (hold it to skim), `Shift+Tab`
steps backward with either Shift key, starting with Shift held begins one
step back, `Esc` cancels with no focus change, releasing Alt commits.

Env: `FAE_HUD_FORCE_OPAQUE=1` (same as `--opaque`),
`FAE_HUD_VERBOSE=1` (what it committed, plus panel geometry).

## Design rules

**It is a viewer, never a mutator — except the one commit.** Nothing in the
panel code focuses, closes, moves or resizes a window. The gesture commits a
single `_NET_ACTIVE_WINDOW` message on release. A drawing bug cannot cost
you a window.

**It is not a resident process.** It paints, holds, fades, exits. Spawned per
Alt+Tab, nothing stays running.

**EWMH only, no WM.** Every property read is standard `_NET_*`. This program
has no idea which window manager is running, so it keeps working if i3 is
ever replaced.

**One entry per window.** Five terminals are five rows with their full
titles — never collapsed, never 16-character stubs.

## The list

Titles come from `_NET_WM_NAME` (UTF-8), `WM_NAME` fallback, and are
ellipsised to the panel width by Pango. Ordering:

1. the ring: our persisted order pruned to live windows, then anything unseen
   in stacking order, topmost first (seeds a cold login)
2. rotated cyclically so the focused window is index 0 — a rotation, not a
   re-sort. Prepending focus destroys the cyclic order and Alt+Tab toggles
   between two windows forever.
3. scoped to `_NET_CURRENT_DESKTOP` (missing `_NET_WM_DESKTOP` counts as here).

The ring file only learns about focus changes we commit. Clicking into a
window with the mouse leaves the tail stale; only the WM's own order would
fix that, and asking it is exactly the coupling this program does not have.

## Regressions worth remembering

- Rotating a ring is not re-sorting it (the toggle bug above).
- The ring appends; move-to-front toggles.
- Escape cancels AND must not commit (it once did both at once).
- `_NET_CLIENT_LIST_STACKING` is static, not recency — never order off it.

## Tests

    make && fae-hud --dump        # is the data there?
    FAE_HUD_VERBOSE=1 fae-hud     # geometry check
    fae-hud --opaque              # the fallback, deliberately

**The test that matters is the walk, and it is not a screenshot.** Drive N
windows through N taps and confirm it walks the ring instead of toggling.
