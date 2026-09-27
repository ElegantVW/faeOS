# fae-hud

The visible layer of the house desktop: a themed X11 panel that shows every
open window and which one has focus.

Built because Alt+Tab worked but told you nothing. You would move focus and
have to guess whether it landed. This is the missing cue.

## Build

    make
    make install      # -> ~/bin/fae-hud
    make clean

No runtime dependencies beyond X11 itself:

| library     | why                                        |
|-------------|--------------------------------------------|
| Xlib        | the window, the properties, the event loop  |
| Xft         | antialiased DejaVu Sans Mono                |
| fontconfig  | finding the face                            |

Core X11 bitmap fonts would have been simpler but would break the house
all-mono rule, so Xft it is.

## Use

    fae-hud                      # highlight _NET_ACTIVE_WINDOW
    fae-hud --focus=0x240000e    # highlight a specific window
    fae-hud --dump               # print the EWMH window list, draw nothing
    fae-hud --display=:1

`fae-cycle` invokes it automatically after every Alt+Tab.

## Design rules

**It is a viewer, never a mutator.** Nothing in this program focuses, closes,
moves or resizes a window. `fae-cycle` owns state changes; the HUD only draws
them. A bug here cannot cost you a window.

**It is not a resident process.** It paints, holds, fades, exits. Spawned per
Alt+Tab, it lives about 1.45s. The rule came out of the i3bar incident, where
a status script needed a daemon and a dying one printed errors all over the
screen. Pressing Alt+Tab repeatedly stacks a few short-lived panels, which
reads as "the list stays up while I cycle" — the behaviour you want anyway.

**EWMH only, no i3.** Every property read here is standard
`_NET_*` / `WM_*`. The program has no idea which window manager is running,
so it keeps working if i3 is ever replaced. That is the seam: the house layer
sits above the WM, not inside its configuration language.

## What is drawn

One row per window, and the list is rotated so the highlighted window is
first — row 0 is "you are here", row 1 is where the next Alt+Tab lands.
Without that rotation the highlight jumps around the panel on every press and
the list is unreadable.

    >  1   0  Red Console                          red-view
       2   0  OC | System audit, documentation…    kitty
       3   2  siren                                siren

- `>` marks the focused window, in house pink, on a pink-tinted band
- the number after it is the workspace (`_NET_WM_DESKTOP`)
- rows on another workspace are dimmed, because cycling to one pulls the view
  across to it — the dimming is the only warning that a jump is coming
- the app class is right-aligned and dimmer than the title

Colours live in `theme.h` and match the `client.*` colours in the i3 config,
so the panel and the window borders agree.

## The fade

Every colour is interpolated between the void and its target over 90ms in,
1100ms hold, 260ms out. Not window opacity — opacity needs a compositor to
honour it, and while picom runs today it may not tomorrow. Interpolating
colours works on a bare X server.

## Two bugs worth remembering

Both were found by looking at the output rather than by reasoning about it.

**Latin-1, not UTF-8.** The first render showed `â€¦` and `Â·` where a
typographic ellipsis and a middle dot should be. `XftDrawString8` decodes
Latin-1 on this system; the `XftDrawStringUtf8` and `XftTextExtentsUtf8`
variants are the ones that handle UTF-8. Everything goes through those now.

**Positions from measured widths.** Laying out columns as multiples of an
assumed character cell drifts, and over a long title it collides with the
column on the right. `measure()` asks Xft for the real advance of every
string and right-aligns against that.

## Known limits

- `_NET_CLIENT_LIST_STACKING` is stacking order, not true MRU. We rotate from
  the focused window, which is what nearly every simple cycler does and is
  indistinguishable from real Alt+Tab in practice. True MRU would mean asking
  i3 for its focus history, which would re-couple us to i3. Not worth it.
- The panel is a dock-type override-redirect window. It never takes focus and
  selects no button events, so clicks pass through to whatever is under it.

## Tests

    make && fae-hud --dump      # is the data there?
    fae-hud --focus=0xID        # does the highlight resolve?

`--dump` exists because the first honest question about a window list is not
"does it look right" but "is the data there" — `_NET_WM_DESKTOP` in
particular is optional, and a handsome render of absent data is still wrong.
