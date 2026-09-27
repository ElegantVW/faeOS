# fae-cascade

Stops new windows from landing exactly on top of each other.

## Why

`for_window [class=".*"] floating enable` in the i3 config floats every new
window at the container's rect, and i3 uses the same rect each time. Open three
terminals and all three sit at `(610,315 700x450)` — literally stacked, so from
outside you see one window and the other two look minimized.

That is not a guess: while auditing `fae-hud` we dumped the i3 tree and found
three windows across three workspaces sharing one identical rect. Combined with
"i3 follows focus across workspaces", it is exactly what "the other windows got
minimized" looks like.

## What it does

Polls `_NET_CLIENT_LIST` every 350ms. When a window appears whose position
**exactly** matches a window already on screen, it nudges it diagonally by
30px per twin — shrinking as it offsets, because moving alone cannot work.

i3 floats a new window at the full container rect: 1873px wide on a 1920px
screen, so there is no room to shift it right. Two earlier attempts logged a
"move" and left all three windows stacked at the same point:

```
0x1e0000e 4 twins at (3,3)     -> (39,69)     clamped back to the original
0x220000e 5 twins at (3,3)     -> (39,69)     same place again
```

Shaving the size as well makes room and gives a proper staircase:

```
0x1e0000e 4 twins (3,3 1873x1003)     -> (153,153 1723x853)
0x220000e 5 twins (3,3 1873x1003)     -> (183,183 1693x823)
0x240000e 6 twins (3,3 1873x1003)     -> (213,213 1663x793)
```

It only ever touches a window that is *exactly* stacked on another, so it never
moves anything on purpose.

## The one resident process in the house

This is deliberate and it is the only exception. It reacts to a window
appearing, and there is no trigger to spawn it from — an Alt+Tab handler cannot
do it, because the cascade has to happen when the window opens, not when you
next press a key. It holds nothing, draws nothing, and prints nothing to the
screen.

**Its first tick adopts the windows already on screen and does nothing.** The
first version did not, treated all six of the user's existing windows as brand
new, and went after them. The log said so plainly:

```
fae-cascade: 0x100000e had 4 twin(s) at (3,3) -> (3,3)
fae-cascade: 0x2200007 had 5 twin(s) at (3,3) -> (3,3)
```

## Unlike fae-hud, this one knows about i3

`fae-hud` is EWMH-only and does not know a window manager exists. `fae-cascade`
moves windows through `i3-msg`, because `XMoveWindow` on a managed window is
fighting the window manager and losing. A tool whose entire job is "fix up how
the WM places things" is not the place to pretend otherwise.

## Build and run

    make
    make install        # -> ~/bin/fae-cascade
    ~/bin/fae-cascade --log=/tmp/fae-cascade.log

| flag       | meaning                                      |
|------------|----------------------------------------------|
| `--log=P`  | where to log (default `/tmp/fae-cascade.log`) |

Start it from the i3 config, not from a shell you are about to close:

    exec --no-startup-id fae-cascade --log=$XDG_RUNTIME_DIR/fae-cascade.log

It exits cleanly on SIGTERM/SIGINT/SIGHUP. X errors are absorbed rather than
fatal: it reads a list of windows and then reads attributes off each one, and a
client can exit in between — the same race that used to kill `fae-hud` with
`BadWindow`.
