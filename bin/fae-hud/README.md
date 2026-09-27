# fae-hud

The visible layer of the house desktop: a themed X11 strip that lists every
open window on the current workspace and shows which one has focus.

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
    fae-hud --cycle              # the Alt+Tab gesture: open, browse, commit once
    fae-hud --dump               # print the window list, draw nothing
    fae-hud --opaque             # the no-compositor fallback, on purpose
    fae-hud --all-workspaces     # include other workspaces (default: current only)
    fae-hud --display=:1

i3 binds `Mod1+Tab` to `~/bin/fae-hud --cycle`.

Env: `FAE_HUD_FORCE_OPAQUE=1` (same as `--opaque`),
`FAE_HUD_VERBOSE=1` (what it committed, plus window geometry from X and cairo).

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

A macOS Cmd+Tab strip, centred horizontally and about a fifth of the way down.

**One entry per window, not per application.** This was per-application first,
as a literal macOS copy, and it was wrong for this machine. Five kitty windows
on one workspace collapsed into a single `kitty` entry, so the strip had one
row, `sel` was 0, and Alt+Tab re-focused the application you were already in —
taps two through eight did literally nothing. A switcher has to enumerate what
you can actually switch between, and on a terminal machine that is windows.

Each entry is the app's icon from `_NET_WM_ICON`, cropped to its visible
content and scaled to fit inside a constant box, with the **window's own
title** beneath it. Apps that publish no icon get a lilac monogram disc
carrying their first letter, so a row is never blank.

    ┌────────────────────────────────────────────────────────┐
    │   ( R )    ( W )     [kit]     [kit]     [kit]        │
    │ Red Con…   window…    ~         OC | Mo…  pixie        │
    ├────────────────────────────────────────────────────────┤
    │              OC | Mount USB and run modded NFS MW      │
    └────────────────────────────────────────────────────────┘

- the selected entry gets a pink plate; the rest are dimmed
- the row label is the window title, ellipsised by Pango to about 16
  characters — which is why the **selected window's full title is repeated on
  its own line** underneath. A 16-character cell cannot make
  `OC | System audit, documentation update…` usefully distinct, and five
  terminals are all titled `~`; the title line is the only place a long title
  is actually readable.
- the list is **rotated** so the focused window is row 0: row 0 is "you are
  here", row 1 is where the next Alt+Tab lands. This is a rotation, not a
  re-sort — see *Three bugs worth remembering*.
- 18px round corners, four diamond corner facets, a hairline rule above the
  title line
- scoped to the current workspace by default. i3 follows focus across
  workspaces, so a switcher that spans them drags you around the machine and
  hides where you started. `--all-workspaces` opts out.

Every colour, dimension and duration lives in `theme.h`, and matches the
`client.*` colours in the i3 config so the strip and the window borders agree.

## Motion

Deliberately almost none. The strip appears fully drawn, focus is committed on
the same event that opened it, and the panel only fades afterwards as
confirmation. Animating the arrival meant the thing you are trying to read was
still arriving while you were already reading it. The only timings are the
250ms fade-out and the 8s keyboard-grab failsafe.

## Translucency, and the no-compositor fallback

With a compositor, the panel uses an ARGB32 visual and cairo's alpha, and you
can read the terminal faintly through it.

Plain X11 **cannot** do per-window alpha — without a compositor the
transparent pixels come out black. So at startup the program checks for an
owned `_NET_WM_CM_S*` selection; if there is none, it drops to the default
visual and a solid fill. Same code path, no visual bug. `FAE_HUD_VERBOSE=1`
reports which mode it chose, and `--opaque` forces the fallback so it can be
tested without stopping picom.

## Three bugs worth remembering

All three were found by looking at output, not by reasoning about it. The
first two are the same bug wearing different clothes, and it is the reason
this program has a `mru.c` at all.

**Rotating a ring is not re-sorting it.** The strip is a ring of windows
rotated so the focused one is row 0. The first implementation prepended the
focused window and then emitted the ring minus it. With ring
`[tE,tD,tC,tB,tA]` and `tD` current, that produced `[tD,tE,tC,tB,tA]` — `tE`
jumped ahead of `tC` purely because it sat at the front of the ring. Row 1 was
then `tE` instead of `tC`, and the next gesture picked `tD` again:

    tap 1: tD -> tE      tap 3: tE -> tD
    tap 2: tE -> tD      tap 4: tD -> tE

A perfect toggle, from code that reads like it does the right thing. The list
must be built by walking the ring *cyclically* from the focused window's slot
and wrapping round to the front.

**Move-to-front is not a ring either.** Textbook MRU — put the committed window
at the front of the list — is what produced that toggle in the first place.
Ring `[A,B,C,D]`, `A` current: one Alt+Tab lands on `B`, correctly. But
rewriting the ring as `[B,A,C,D]` means the next gesture computes "the one
after `B`", which is `A`, the window you just left. `mru.c` therefore prunes
dead ids, keeps every survivor in its slot, and only ever *appends* something
new. Appending is what grows the ring to the full window set on the first
commit; inserting at the front would reverse the cyclic order and bring the
first bug straight back.

An intermediate attempt made it worse in an instructive way: recording only
the window we had committed left the ring one entry long, so the rest of the
list fell back to `_NET_CLIENT_LIST_STACKING` — which is static, and puts the
topmost window immediately after the current one. The ring grew `1, 2, 1, 2`.
`_NET_CLIENT_LIST_STACKING` is not recency; it was measured by focusing the
bottom-most window in the stack and reading the property again, and it came
back byte-for-byte identical.

**Escape committed instead of cancelling.** The cancel branch set
`cancelled = 1` *and then called `commit()`*, so Escape moved focus to the
highlighted window; the release-commit further down was correctly skipped, so
the code cancelled and committed simultaneously. Measured at 20ms, 50ms, 120ms
and 300ms holds — every way a person can press a key. Cancelling is now just
`cancelled = 1`.

The older Xft-era bugs (Latin-1 decoding by `XftDrawString8`, the footer
lighting up under an empty body, the focus band reaching into the header rule,
assumed character cells colliding with a real column) are in the changelog.
Pango removed the first and the last; the panel is a single-piece strip now,
so the middle two cannot recur.

## Glyph coverage

The strip draws **no decorative glyphs at all**. The earlier vertical panel
used `◈`/`◇` to mark the focused row and a `⌘` in the footer; the strip
carries the same distinction with a pink plate and opacity instead, and at
11–13px `◈` read as a plain filled diamond anyway. There is no `THEME_GLYPH_*`
block left in `theme.h`.

Two text dependencies remain, both worth knowing about:

- `PANGO_ELLIPSIZE_END` inserts `…` U+2026 when it truncates a long title. It
  is in DejaVu Sans Mono. Verify with
  `fc-list ':charset=2026' family` on a machine with different fontconfig.
- The monogram disc for an app that publishes no `_NET_WM_ICON` takes the
  first character of its `WM_CLASS`, so it is always ASCII from the app
  itself.

The older `⬡` U+2B21 note still holds if the vocabulary ever comes back: the
installed face has no hexagons, which is why the house builds from diamonds.

## Known limits

- **The ring only learns about focus changes we make.** It is our own file, not
  the window manager's. If you click into a terminal with the mouse, the
  *current* window is still correct — `_NET_ACTIVE_WINDOW` is read fresh on
  every invocation — but the tail of the list does not learn about it. Only
  i3's own tree order would fix that, and asking i3 is exactly the coupling
  this program does not have.
- The strip is a dock-type override-redirect window. It never takes focus and
  selects no button events, so clicks pass through to whatever is under it.
- It sets `_NET_WM_NAME` *and* `WM_NAME`, because `_NET_WM_NAME` alone leaves
  the window invisible to `xdotool search` and `wmctrl`, which is maddening
  when you are trying to measure it.
- With one window on the workspace, Alt+Tab shows the strip briefly and
  changes nothing. That is deliberate: the old per-application build
  re-focused the window you were already on, which is not a no-op, it is a
  pointless focus change.

## Tests

    make && fae-hud --dump        # is the data there?
    FAE_HUD_VERBOSE=1 fae-hud     # which visual, and what geometry?
    fae-hud --opaque              # the fallback, deliberately

`--dump` exists because the first honest question about a window list is not
"does it look right" but "is the data there" — `_NET_WM_DESKTOP` in
particular is optional, and a handsome render of absent data is still wrong.

**The test that matters is the walk, and it is not a screenshot.** Drive N
taps and log where focus lands at each step. With N windows the first N hops
must be N *distinct* windows and hop N+1 must equal hop 1. A toggle passes
every visual check — the strip looks right, the highlight moves, focus changes
— and fails only this. Both ordering bugs above survived a handsome render
and were caught in one run of this.

Two rules for driving it, both learned the hard way:

- **Release Alt while the gesture is live.** `xdotool keydown alt; fae-hud
  --cycle; xdotool keyup alt` deadlocks: the program is holding the keyboard
  waiting for Alt to come up, and Alt only comes up after it returns. Each tap
  then burns the full 8s failsafe. Run the binary in the background, sleep,
  then release Alt.
- **Check the exit status, not the absence of output.** A hung gesture still
  exits 0 after the failsafe.

`FAE_HUD_VERBOSE=1` prints what it committed (`release -> <title>`,
`selection -> N`, `cancelled by Escape`) and the window geometry from both X
and cairo. Note that `XGetGeometry` writes to *both* trailing out-parameters;
passing `NULL` for the depth segfaults inside Xlib.


## Three things that are not ours to fix, and bit us

All three are picom or pango, and all three cost more time than the code they
broke.

**picom was making the strip see-through.** The panel declares itself
`_NET_WM_WINDOW_TYPE_DOCK`, so picom classified it as an *inactive* window and
applied `inactive-opacity = 0.92` to it — no matter what alpha cairo filled the
surface with. And `round-borders = 12` was rounding the panel's corners,
clipping the ones cairo drew and cutting the corner facets.

**picom was also drawing a shadow around the strip.** `shadow = true` with
`shadow-radius = 12` and `shadow-offset-x/y = -8`, and `shadow-exclude` listed
only i3bar and rofi. The visible result was a blurred dark frame around the
panel that read exactly like the panel being inset inside its own window:
measured, `c_void` filled the window edge to edge while the panel sat
`396x126` inside `432x164`. The window was never the wrong size — X and cairo
both reported `432x164` — and the shadow was sitting on top of it. Note that
`rounding-exclude` did *not* cover this; shadows are a separate rule. Both are
now excluded by name, and the frame is gone (0 void pixels inside the window,
was a full 18px band on all four sides).

**`pango_cairo_show_layout` positions by the layout's top-left, not the text
baseline.** Every `y` in the paint code is therefore a top edge. Treating it
as a baseline is what put the window-count number *underneath* its badge
instead of inside it.

## A note on verification

Several apparent rendering bugs this round turned out to be my own
stale-coordinate misreads, twice over. The strip's width and position change
with the number of windows, so a crop taken using the geometry from an earlier
run lands beside the panel and shows desktop instead.

The sharper version of the mistake: I captured a frame, then ran the program
*again* to read its geometry, and compared the two. The window set had changed
between the runs, so the "18px inset" I spent a while chasing was me measuring
one run's pixels against another run's numbers. **Capture and read the geometry
from the same run** — pipe stderr to a file alongside the screenshot. When the
two disagree, believe the numbers that came from the same process.

Pixel sampling of known points settles what is actually on screen: `c_panel`
`(42,21,32)` at the panel centre, `c_void` `(10,5,8)`, desktop `(38,35,53)`.
A misaligned crop does not. And when the geometry is genuinely in doubt, log
what X and cairo each say rather than inferring it from a picture.

## Building on the icon path

`_NET_WM_ICON` really is populated — kitty publishes a 128x128 image plus three
small ones. Do not check this with `xprop`: this system's xprop renders
CARDINAL icon data as coloured blocks, which reads exactly like an empty
property. The property is read directly in C, so that is all moot.
