# fae-wm

**Jana** — the house window manager. Tiling by default, EWMH-serving, X11,
written in C. Jana spins the rooms: new windows split the focused cell,
games and Big Picture take the glass, Super+d is the in-house launcher.

The Alt+Tab switcher is built in and reads the WM's own focus stack: exact
recency, mouse clicks included, no ring file, no grab races.

## Build

    make
    make install      # -> ~/bin/fae-wm
    make clean

Needs: Xlib, cairo, pangocairo (same as the old switcher had).

## Trying it

fae-wm is the session window manager (`.xinitrc` hands the session to it
after the seal greeter). Log out and back in to pick up a fresh build.

## Use

Alt+Tab opens the panel (pre-stepped one), Tab walks forward (hold to
skim), Shift+Tab walks back with either Shift, Esc cancels silently,
releasing Alt commits. A tap steps once.

Keys (rebindable, see Config):

- `Super+h` help overlay
- `Super+d` launch (pins + `.desktop`)
- `Super+Shift+q` close · `Super+m` minimize · `Super+Shift+f` maximize · `Super+f` fullscreen
- `Super+v` / `Super+s` next split stacked / side-by-side
- `Super+e` even split · `Super+t` dwindle / master-stack
- `Super+r` then hjkl grow the split (tile) or resize (float)
- `Super+Shift+Space` float / tile
- `Super+j/k/l/;` focus · `Super+Shift+j/k/l/;` swap (tiled) or nudge (float)
- `Super+Return` terminal · `Super+1..0` workspaces
- `Super+=` / `Super+-` dock size (0.80 … 2.00, persisted as `dock_scale`)
- Click focuses+raises · `Super+drag` moves · `Super+right-drag` resizes (float)

## Config

`$FAE_WM_CONFIG` or `~/.config/fae-wm/config`. Missing file is fine:
built-in defaults stand in. Lines:

    gap 4
    border 2
    color_focus #e879a0
    color_unfocus #9d5c75
    bind Mod4+Return exec kitty
    bind Mod4+Shift+q close
    bind Mod4+j focus left
    bind Mod4+1 workspace 1
    bind Mod4+Shift+1 toworkspace 1
    exec picom --config ~/.config/picom/picom.conf
    dock_dwell 280
    dock_hotspot center
    dock_scale 1.00

Actions: `exec`, `close`, `fullscreen`, `focus <dir>`, `move <dir>`,
`workspace <n>`, `toworkspace <n>`, `resize-mode`, `preset
<left|right|top|center>`, `reload`, `quit`, `help`, `launch`,
`dock-scale <up|down>`.
Modifiers: `Mod1/Alt`, `Mod4/Super`, `Shift`, `Ctrl`. `fae-wm --check`
validates and prints what it loaded.

## Design rules

- **Tiling by default.** New windows split the focused cell by shape (wide → columns, tall → rows), land on the side you last walked, and leave focus ~62%. `Super+v`/`s` override the next split only. Dialogs float. Super+Shift+Space toggles.
- **Border-only frames.** No titlebar. Focus is a 2 px pink border. Fullscreen has none.
- **EWMH served, never depended on.** Client list, stacking, active window,
  desktops, fullscreen state, close semantics — published for bars, pagers
  and scripts. Our own focus stack is internal and exact.
- **Viewer/mutator split kept where it matters:** the panel only draws;
  the gesture commits one focus change.
- **Remembered bugs, encoded:** rotate-don't-resort, append-don't-prepend,
  Esc-never-commits, stacking-is-not-recency (moot inside, kept as comments).

## Known gaps (v1)

- No titlebars (borders only). No tabbed/stacked/scratchpad/marks.
- `fae-cycle` speaks i3-msg and stays an i3-session tool; the built-in
  switcher covers its job here.
- Withdrawn (minimized) windows are forgotten until remapped.

## Dock

Bottom-center **starship capsule**: pink glass stadium with circular wells.
Top band is `✦ user ✦ · HH:MM · RAM · CPU · HDD · temp`. Wells hold the
whole house sigil, scaled to fit. Footer is music, unread mail, focused
window. Hover lifts a well. Width follows the icons; status ellipsizes.
`Super+=` / `Super+-` size. `make test` is hotspot/dwell/scale/fit.
Log out after `make install`.
