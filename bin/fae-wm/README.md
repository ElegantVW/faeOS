# fae-wm

The house window manager. Floating-first, EWMH-serving, X11, written in C.
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
- `Super+Shift+q` close · `Super+m` minimize · `Super+Shift+f` maximize · `Super+f` fullscreen
- `Super+v` / `Super+s` next split stacked / side-by-side
- `Super+Shift+Space` float / tile
- `Super+j/k/l/;` focus · `Super+Shift+j/k/l/;` swap (tiled) or nudge (float)
- `Super+Return` terminal · `Super+1..0` workspaces
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

Actions: `exec`, `close`, `fullscreen`, `focus <dir>`, `move <dir>`,
`workspace <n>`, `toworkspace <n>`, `resize-mode`, `preset
<left|right|top|center>`, `reload`, `quit`. Modifiers: `Mod1/Alt`,
`Mod4/Super`, `Shift`, `Ctrl`. `fae-wm --check` validates and prints
what it loaded.

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

- No titlebars (borders only). No tiling layouts (floating-first by design;
  optional later). No scratchpad/marks.
- `fae-cycle` speaks i3-msg and stays an i3-session tool; the built-in
  switcher covers its job here.
- Withdrawn (minimized) windows are forgotten until remapped.

## Dock

Bottom-center overlay. It rises after a short dwell in the **center** of the
bottom edge (not the whole screen). Glass pill, squircle wells, label only
on hover, pixmap back-buffer (no 60 Hz raise). `make test` checks hotspot /
dwell / labels without X. Log out and back in after `make install`.
