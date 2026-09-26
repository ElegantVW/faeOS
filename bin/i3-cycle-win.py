#!/usr/bin/env python3
"""i3-cycle-win — MRU-ish window cycling for faeOS (Alt+Tab).

Usage: i3-cycle-win.py next|prev
Walks all managed windows in tree order, cyclically, focusing the next
(or previous) one after the currently focused window. Scratchpad-hidden
windows are skipped (use fae-win to summon those).

Needs: i3-msg on PATH, DISPLAY set (your session, not headless).
"""
import json
import subprocess
import sys


def i3msg(*args):
    out = subprocess.run(
        ["i3-msg", "-t", *args], capture_output=True, text=True, check=False
    )
    return out.stdout


def collect(node, wins, focused):
    """Depth-first leaves with real windows; record focused id."""
    if node.get("focused"):
        focused.append(node.get("id"))
    if node.get("window") and node.get("scratchpad_state", "none") == "none":
        wins.append(node["id"])
    for ch in node.get("nodes", []) + node.get("floating_nodes", []):
        collect(ch, wins, focused)


def main() -> int:
    direction = sys.argv[1] if len(sys.argv) > 1 else "next"
    step = -1 if direction == "prev" else 1
    try:
        tree = json.loads(i3msg("get_tree"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"i3-cycle-win: no tree ({e})", file=sys.stderr)
        return 1
    wins, focused = [], []
    collect(tree, wins, focused)
    if not wins:
        return 0
    if len(wins) == 1 or not focused:
        target = wins[0]
    else:
        try:
            i = wins.index(focused[0])
        except ValueError:
            i = 0 if step > 0 else 1
        target = wins[(i + step) % len(wins)]
    subprocess.run(
        ["i3-msg", f"[con_id={target}]", "focus"],
        capture_output=True, check=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
