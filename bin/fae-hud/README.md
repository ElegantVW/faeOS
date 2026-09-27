# fae-hud

The visible layer of the house desktop: a themed X11 panel that lists every
open window and shows which one has focus.

Built because Alt+Tab worked but told you nothing. You would move focus and
have to guess whether it landed. This is the missing cue.

## Build

    make
    make install      # -> ~/bin/fae-hud
    make clean

| library    | why                                                     |
|------------|---------------------------------------------------------|
| Xlib       | the window, its properties, the event loop              |
| cairo      | the drawing: round corners and per-pixel alpha both need it |
| pangocairo | shaped, ellipsised text                                  |

The first version used Xft and claimed "no runtime dependencies beyond X11".
That is no longer true, and it is a deliberate trade: Xft has **no arc
primitive** — only `Rect`, `String`, `Glyphs` — so it cannot round a corner at
all, and the panel was a hard rectangle. Any softness you saw was picom's
shadow, not our drawing. Cairo also gives genuine translucency, which X11
cannot do on its own.

## Use

    fae-hud                      # highlight _NET_ACTIVE_WINDOW
    fae-hud --focus=0x240000e    # highlight a specific window
    fae-hud --dump               # print the EWMH window list, draw nothing
    fae-hud --opaque             # the no-compositor fallback, on purpose
    fae-hud --display=:1

`fae-cycle` invokes it automatically after every Alt+Tab.

Env: `FAE_HUD_FORCE_OPAQUE=1` (same as `--opaque`),
`FAE_HUD_VERBOSE=1` (report the chosen visual and geometry to stderr).

## Design rules

**It is a viewer, never a mutator.** Nothing in this program focuses, closes,
moves or resizes a window. `fae-cycle` owns state changes; the HUD only draws
them. A bug here cannot cost you a window.

**It is not a resident process.** It paints, holds, fades, exits — about 1.65s
for two windows. Spawned per Alt+Tab, nothing needs to stay running. The rule
came from the i3bar incident, where a status script needed a daemon and a
dying one printed errors across the screen. Pressing Alt+Tab repeatedly stacks
a few short-lived panels, which reads as "the list stays up while I cycle".

**EWMH only, no i3.** Every property read is standard `_NET_*` / `WM_*`. The
program has no idea which window manager is running, so it keeps working if i3
is ever replaced. That is the seam: the house layer sits above the WM, not
inside its configuration language.

## What is drawn

Two lines per window, so the panel spends height instead of width.

    ◆ windows ────────────────────────── 3 ┐
                                          │
    ◆  OC | Creating a comprehensive…      │   ◈ focused: pink, banded
       0 · kitty                           │
                                          │
    ◇  ~                                   │   ◇ idle, dimmer
       1 · kitty                           │
                                          │
    ◇  A deliberately long title to sho…   │   Pango ellipsises
       0 · hudt                            │
    ┌────────────────────────────────────┐│
    │ alt+tab next · alt+shift+tab back   ││
    └────────────────────────────────────┘┘

- `◈` marks the focused row, `◇` the rest
- each row's second line is `workspace · app class`
- rows on another workspace are dimmed, because cycling to one pulls the view
  across to it — the dimming is the only warning that a jump is coming
- the list is rotated so the focused window is row 0: row 0 is "you are here",
  row 1 is where the next Alt+Tab lands. Without the rotation the highlight
  jumps around the panel on every press and the list is unreadable.
- 14px round corners, four diamond corner facets, a hairline rule under the
  header and above the footer, a hairline separating the glyph column from
  the text, and a soft pink glow around the whole thing

Width is content-driven, floored at 470 and capped at `min(560, 34% of
screen)`. Tall stacks of windows stay inside the screen: past 14 rows the
panel says `+N more` instead of growing without bound.

Every colour, dimension, duration and glyph lives in `theme.h`, and matches
the `client.*` colours in the i3 config so the panel and the window borders
agree.

## Motion

    0ms      panel blooms: inset 14 -> 0, alpha 0 -> 1     130ms
    15ms     header and corner facets
    60ms     row 0, each row +22ms, each 130ms            staggered
    200ms    focused band wipes in from the left          180ms
             hold                                          1200ms
    ~1.43s   footer arrives with the last row
             fade out                                      220ms

The bloom animates an *inner* rounded rect rather than resizing the window,
so there is no resize flicker.

## Translucency, and the no-compositor fallback

With a compositor, the panel uses an ARGB32 visual and cairo's alpha, and you
can read the terminal faintly through it.

Plain X11 **cannot** do per-window alpha — without a compositor the
transparent pixels come out black. So at startup the program checks for an
owned `_NET_WM_CM_S*` selection; if there is none, it drops to the default
visual and a solid fill. Same code path, no visual bug. `FAE_HUD_VERBOSE=1`
reports which mode it chose, and `--opaque` forces the fallback so it can be
tested without stopping picom.

## Four bugs worth remembering

All four were found by looking at output, not by reasoning about it.

**Latin-1, not UTF-8.** The first Xft render showed `â€¦` and `Â·` where a
typographic ellipsis and a middle dot should be. `XftDrawString8` decodes
Latin-1 on this system. Pango removes the whole class of problem, and
`PANGO_ELLIPSIZE_END` replaced a hand-rolled truncation.

**The footer lit up under an empty body.** The panel bloomed as one piece but
the type assembled row by row, and the header and footer rode the *global*
envelope. At 80ms you got a fully-lit footer sitting under zero rows, which
reads as a bug rather than as motion. They now join the cascade.

**The band reached into the header rule.** It was drawn `row_h` tall, and
`row_h` includes the 12px gap *under* a row. It now hugs the row's two lines.

**Columns collided.** Laying out by an assumed character cell drifts, and over
a long title it ran into the column on the right. Pango measures the real
advance now.

## Glyph coverage

Verified against the installed face with `fc-list ':charset=2B21' family`:

| wanted        | have it | note                              |
|---------------|---------|-----------------------------------|
| `◈` U+25C8    | yes     | focused row, header               |
| `◇` U+25C7    | yes     | idle row                          |
| `·` U+00B7    | yes     | separators                        |
| `⬡` U+2B21    | **no**  | hexagons — the crystal vocabulary is built from diamonds instead |
| `⌘` U+2318    | **no**  | so the footer keeps plain `alt+tab` |

At 11–13px `◈` reads as a filled diamond rather than a diamond-in-a-diamond,
so the focused/idle distinction is carried by filled-vs-hollow and by the pink
band, not by the glyph alone.

All of it is in the `THEME_GLYPH_*` block in `theme.h`, so a substitution on a
machine with a different fontconfig is a one-line change.

## Known limits

- `_NET_CLIENT_LIST_STACKING` is stacking order, not true MRU. We rotate from
  the focused window, which is what nearly every simple cycler does and is
  indistinguishable from real Alt+Tab in practice. True MRU would mean asking
  i3 for its focus history, which would re-couple us to i3.
- The panel is a dock-type override-redirect window. It never takes focus and
  selects no button events, so clicks pass through to whatever is under it.
- It sets `_NET_WM_NAME` *and* `WM_NAME`, because `_NET_WM_NAME` alone leaves
  the window invisible to `xdotool search` and `wmctrl`, which is maddening
  when you are trying to measure it.

## Tests

    make && fae-hud --dump        # is the data there?
    FAE_HUD_VERBOSE=1 fae-hud     # which visual, and what geometry?
    fae-hud --opaque              # the fallback, deliberately

`--dump` exists because the first honest question about a window list is not
"does it look right" but "is the data there" — `_NET_WM_DESKTOP` in
particular is optional, and a handsome render of absent data is still wrong.

For the motion, capture frames across the timeline and look at each one. A
single screenshot cannot show a cascade; the frame at 80ms is where the
footer bug was visible.
