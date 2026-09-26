#!/usr/bin/env python3
"""sigil2story — 9:16 story SVG from a CP437 sigil (then rsvg-convert to PNG).

Usage: sigil2story.py SIGIL.TXT --color HEX --name NAME --sub SUB --repo URL --out STORY.SVG
"""
import argparse
import html
import sys

NIGHT = "#1A1218"
PARCHMENT = "#F0E4EE"
DUSK = "#6B6FA8"
MONO = "DejaVu Sans Mono, Menlo, Consolas, monospace"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sigil")
    ap.add_argument("--color", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--sub", default="")
    ap.add_argument("--repo", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.sigil) as f:
        rows = [r for r in f.read().splitlines() if r.strip()]
    if not rows:
        print("empty sigil", file=sys.stderr)
        return 1

    W, H = 1080, 1920
    cx = W // 2
    fs, lh = 76, 88
    top = 420
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f'<rect width="{W}" height="{H}" fill="{NIGHT}"/>',
        f'<g font-family="{MONO}" font-size="{fs}" text-anchor="middle">',
    ]
    for i, row in enumerate(rows):
        parts.append(
            f'<text x="{cx}" y="{top + i * lh}" fill="{html.escape(args.color)}">{html.escape(row)}</text>'
        )
    parts.append("</g>")
    name_y = top + len(rows) * lh + 160
    parts.append(
        f'<text x="{cx}" y="{name_y}" fill="{PARCHMENT}" font-family="{MONO}" font-size="84" font-weight="bold" text-anchor="middle">{html.escape(args.name)}</text>'
    )
    if args.sub:
        parts.append(
            f'<text x="{cx}" y="{name_y + 80}" fill="{DUSK}" font-family="{MONO}" font-size="38" text-anchor="middle">{html.escape(args.sub)}</text>'
        )
    if args.repo:
        parts.append(
            f'<text x="{cx}" y="{H - 140}" fill="{DUSK}" font-family="{MONO}" font-size="32" text-anchor="middle">{html.escape(args.repo)}</text>'
        )
    parts.append("</svg>")
    with open(args.out, "w") as f:
        f.write("\n".join(parts) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
