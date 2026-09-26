#!/usr/bin/env bash
# make.sh — automated content capture: run stuff, grab frames, assemble GIFs.
# v1: terminal shots via kitty remote, window shots via Xvfb + ffmpeg,
# GIFs via two-pass palette. Prints a verification checklist at the end.
#
# Usage: ./make.sh [shots|gifs|windows|all]   (default: shots)
# Env: KITTY_SOCK (default unix:/tmp/opencode/kitty.sock), SHOTS_DIR.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
KITTY_SOCK="${KITTY_SOCK:-unix:/tmp/opencode/kitty.sock}"
SHOTS_DIR="${SHOTS_DIR:-/tmp/opencode/shots}"
MODE="${1:-shots}"
mkdir -p "$SHOTS_DIR"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; return 1; }; }
need ffmpeg; need python3

autocrop() { # $1 src $2 dst
  python3 - "$1" "$2" <<'PYEOF'
import sys
from PIL import Image
import numpy as np
src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB")
a = np.asarray(im)
ys, xs = (lambda m: (m[0], m[1]))(__import__("numpy").where((a.sum(axis=2) > 12)))
if len(xs) == 0:
    print(f"BLANK: {src}"); sys.exit(3)
x0, x1 = max(0, xs.min() - 12), min(im.width, xs.max() + 13)
y0, y1 = max(0, ys.min() - 12), min(im.height, ys.max() + 13)
im.crop((x0, y0, x1, y1)).save(dst)
print(f"shot: {dst} {(x1 - x0)}x{(y1 - y0)}")
PYEOF
}

gif_of() { # $1 mp4 $2 gif
  local mp4="$1" gif="$2" pal="$SHOTS_DIR/.pal.png"
  ffmpeg -y -v error -i "$mp4" -vf "fps=10,scale=640:-1:flags=lanczos,palettegen" "$pal"
  ffmpeg -y -v error -i "$mp4" -i "$pal" -lavfi "fps=10,scale=640:-1:flags=lanczos [x]; [x][1:v] paletteuse" "$gif"
  local kb; kb=$(du -k "$gif" | cut -f1)
  echo "gif: $gif ${kb}KB"
  if (( kb > 5120 )); then echo "WARN: $gif over 5MB" >&2; fi
}

case "$MODE" in
  shots|gifs|windows|all) ;;
  *) echo "usage: $0 [shots|gifs|windows|all]" >&2; exit 1 ;;
esac

echo "== $MODE → $SHOTS_DIR =="
echo "(v1 skeleton: flows mirror tools/content/shots.yaml; full YAML driver lands next.)"
echo "kitty: $KITTY_SOCK"
kitty @ --to "$KITTY_SOCK" ls >/dev/null && echo "kitty remote: OK" || echo "kitty remote: DOWN"
echo "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1)"
echo
echo "checklist:"
echo "  [ ] every PNG opens and shows its named subject"
echo "  [ ] every GIF < 5MB and visibly moves (or is captioned static)"
echo "  [ ] no secrets/PII in any frame (mail bodies, keys, client names)"
echo "  [ ] sources committed under <repo>/assets/screenshots/, README embedded"
