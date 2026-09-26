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

kitty_send() { # $1 text (kitty @ send-text understands backslash escapes)
  kitty @ --to "$KITTY_SOCK" send-text "$1"
}

kitty_text() { # tail of current terminal text
  kitty @ --to "$KITTY_SOCK" get-text 2>/dev/null | tail -6
}

clean_prompt() { # quit stray TUIs until a fresh prompt line is last
  for _ in 1 2 3; do
    if kitty_text | grep -q "Kindling the prompt flame"; then return 0; fi
    kitty_send 'q'; sleep 1
  done
  kitty_text | grep -q "Kindling the prompt flame"
}

run_sequence() { # $1 entry — record a tested recipe, see shots.yaml sequences
  local entry="$1" take="$SHOTS_DIR/${entry}-take.mp4" rec
  clean_prompt || { echo "no clean prompt; abort" >&2; return 1; }
  case "$entry" in
    kindling)
      ffmpeg -y -v error -f x11grab -framerate 10 -i :99 -t 150 "$take" &
      rec=$!; sleep 2
      kitty_send 'cd ~/fae-kernel && make kindle\n'; sleep 14
      kitty_send 'make below\n'; sleep 120
      wait $rec
      ;;
    bulwark)
      ffmpeg -y -v error -f x11grab -framerate 10 -i :99 -t 110 "$take" &
      rec=$!; sleep 2
      kitty_send '~/bin/bulwark tour\n'; sleep 5
      for _ in 1 2 3 4 5 6 7; do kitty_send '\r'; sleep 5; done
      kitty_send 'q'; sleep 1
      kitty_send '~/bin/bulwark status\n'; sleep 6
      kitty_send '~/bin/bulwark ward\n'; sleep 8
      kitty_send '~/bin/bulwark sentinel\n'; sleep 8
      wait $rec
      ;;
    pixie)
      ffmpeg -y -v error -f x11grab -framerate 10 -i :99 -t 95 "$take" &
      rec=$!; sleep 2
      kitty_send '~/bin/menagerie set pixie qwen3-4b-instruct-q4_k_m\n'; sleep 22
      kitty_send '~/bin/pixie "haiku about my terminal"\n'; sleep 45
      kitty_send '~/bin/menagerie status all\n'; sleep 10
      kitty_send '~/bin/menagerie set pixie Huihui-Qwen3-8B-abliterated-v2.i1-Q4_K_M\n'; sleep 12
      wait $rec
      ;;
    siren)
      ffmpeg -y -v error -f x11grab -framerate 10 -i :99 -t 90 "$take" &
      rec=$!; sleep 2
      kitty_send '~/bin/siren\n'; sleep 4
      kitty_send '\r'; sleep 4
      kitty_send '\t'; sleep 4
      kitty_send '\t'; sleep 4
      kitty_send 'q'; sleep 2
      kitty_send '~/bin/siren audio\n'; sleep 6
      kitty_send '~/bin/siren trove music lofi\n'; sleep 25
      kitty_send 'q'; sleep 2
      wait $rec
      ;;
    faeos)
      ffmpeg -y -v error -f x11grab -framerate 10 -i :99 -t 75 "$take" &
      rec=$!; sleep 2
      kitty_send '~/bin/scry --help\n'; sleep 7
      kitty_send '~/bin/menagerie status all\n'; sleep 9
      kitty_send 'head -30 ~/faeOS/docs/cli-voice.md\n'; sleep 8
      kitty_send '~/bin/kur --help\n'; sleep 7
      kitty_send '~/bin/magpie --help\n'; sleep 7
      kitty_send 'true\n'; sleep 3
      wait $rec
      ;;
  esac
  echo "take: $take"
  echo "next: trim tail, xfade story bumper, verify contact sheet, commit to grove/assets/sequences/"
}

case "$MODE" in
  shots|gifs|windows|all) ;;
  sequence)
    ENTRY="${2:-}"
    case "$ENTRY" in
      kindling|bulwark|pixie|siren|faeos) run_sequence "$ENTRY" ;;
      *) echo "sequences: kindling bulwark pixie siren faeos (goblin/seal/fairy need hands or accounts)" >&2; exit 1 ;;
    esac
    exit 0
    ;;
  *) echo "usage: $0 [shots|gifs|windows|all|sequence NAME]" >&2; exit 1 ;;
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
