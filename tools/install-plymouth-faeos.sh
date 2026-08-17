#!/usr/bin/env bash
# Install faeOS Plymouth theme + quiet splash cmdline notes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
THEME_SRC="$ROOT/assets/plymouth/faeos"
THEME_DST="/usr/share/plymouth/themes/faeos"

echo "==> generate assets"
python3 "$ROOT/tools/make_plymouth_assets.py"

echo "==> install theme → $THEME_DST"
sudo mkdir -p "$THEME_DST"
sudo cp -a "$THEME_SRC"/. "$THEME_DST"/
sudo plymouth-set-default-theme faeos
echo "    default theme: $(plymouth-set-default-theme)"

echo "==> done (still need: mkinitcpio hooks, kernel cmdline, mkinitcpio -p linux)"
