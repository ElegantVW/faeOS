#!/usr/bin/env python3
"""sigil2svg — render a CP437 sigil .txt into a house-palette SVG hero.

Usage: sigil2svg.py SIGIL.TXT --color HEX --name NAME [--sub SUB] --out HERO.SVG
Source of truth stays the .txt; this output is decoration for repo pages.
"""
import argparse
import html
import sys

NIGHT = "#1A1218"
PARCHMENT = "#F0E4EE"
DUSK = "#6B6FA8"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sigil")
    ap.add_argument("--color", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--sub", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=360)
    args = ap.parse_args()

    with open(args.sigil) as f:
        rows = f.read().splitlines()
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    if not rows:
        print("empty sigil", file=sys.stderr)
        return 1

    W, H = args.width, args.height
    fs = 26
    lh = 30
    block_h = len(rows) * lh
    name_y = (H + block_h) // 2 + 52
    top = (H - block_h) // 2 - 30
    cx = W // 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f'<rect width="{W}" height="{H}" fill="{NIGHT}"/>',
        f'<g font-family="DejaVu Sans Mono, Menlo, Consolas, monospace" font-size="{fs}" text-anchor="middle">',
    ]
    for i, row in enumerate(rows):
        y = top + i * lh + fs
        parts.append(
            f'<text x="{cx}" y="{y}" fill="{html.escape(args.color)}">{html.escape(row)}</text>'
        )
    parts.append("</g>")
    parts.append(
        f'<text x="{cx}" y="{name_y}" fill="{PARCHMENT}" font-family="Fraunces, Georgia, serif" font-size="36" text-anchor="middle">{html.escape(args.name)}</text>'
    )
    if args.sub:
        parts.append(
            f'<text x="{cx}" y="{name_y + 30}" fill="{DUSK}" font-family="DejaVu Sans Mono, monospace" font-size="16" text-anchor="middle">{html.escape(args.sub)}</text>'
        )
    parts.append("</svg>")
    with open(args.out, "w") as f:
        f.write("\n".join(parts) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
