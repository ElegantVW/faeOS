#!/usr/bin/env bash
# fae-bootstrap.sh — Fresh Arch Linux → full faeOS in one command
#
# Usage (after cloning):
#   cd ~/faeos && bash fae-bootstrap.sh
#
# Or from GitHub directly:
#   bash <(curl -sL https://raw.githubusercontent.com/ElegantVW/faeOS/main/fae-bootstrap.sh)

set -euo pipefail

echo "╭─ ✦ faeOS Bootstrap ✦ ─╮"
echo

# ── Dependencies ──────────────────────────────────────────────
echo "==> Installing Arch packages (sudo required)"
if [[ -f pkglist.txt ]]; then
  sudo pacman -S --needed --noconfirm $(grep -v '^#' pkglist.txt | grep -v '^$')
else
  sudo pacman -S --needed --noconfirm zsh starship kitty i3-wm picom feh rofi \
    ttf-dejavu ttf-dejavu-nerd python3 git pipewire wireplumber \
    mpv yt-dlp ddgr dunst gtk3 qt5ct
fi

# ── Default shell ────────────────────────────────────────────
if [[ "$SHELL" != /usr/bin/zsh ]]; then
  echo "==> Setting zsh as default shell"
  chsh -s /usr/bin/zsh
fi

# ── Install faeOS ────────────────────────────────────────────
echo "==> Running install.sh"
bash install.sh

# ── Desktop configs ──────────────────────────────────────────
echo "==> Installing desktop configs"

mkdir -p ~/.config/{kitty,i3,picom,kmscon,rofi,gtk-3.0,dunst}
mkdir -p ~/.config/qt5ct
mkdir -p ~/Pictures

# Terminal
cp -f config/kitty/kitty.conf ~/.config/kitty/
cp -f config/kmscon/kmscon.conf ~/.config/kmscon/

# Window manager
cp -f config/i3/config ~/.config/i3/
cp -f config/picom/picom.conf ~/.config/picom/
cp -f config/picom/crt.frag ~/.config/picom/

# Theme
cp -f config/gtk/settings.ini ~/.config/gtk-3.0/
mkdir -p ~/.config/gtk-4.0
cp -f config/gtk/settings.ini ~/.config/gtk-4.0/
cp -f config/rofi/pixie.rasi ~/.config/rofi/
cp -f config/dunst/dunstrc ~/.config/dunst/
cp -f config/qt/qt5ct.conf ~/.config/qt5ct/

# Wallpaper
if [[ -f assets/wall.png ]]; then
  cp -f assets/wall.png ~/Pictures/
  echo "==> Wallpaper → ~/Pictures/wall.png"
fi

# ── User services (optional) ─────────────────────────────────
echo
# ── PAM config for seal ────────────────────────────────
if [ -f config/seal.pam ] && [ ! -f /etc/pam.d/seal ]; then
  echo "==> Installing PAM config for seal"
  sudo cp config/seal.pam /etc/pam.d/seal
fi

echo "==> Enabling user services"
systemctl --user daemon-reload 2>/dev/null || true

for svc in goblin-sync.timer ether-bridge.service bulwark-sentinel.timer seald.service hearth.service; do
  if systemctl --user enable --now "$svc" 2>/dev/null; then
    echo "    enabled: $svc"
  else
    echo "    skip:    $svc (not available yet)"
  fi
done

# ── Post-setup ───────────────────────────────────────────────
echo
echo "╭─ ✦ Bootstrap complete ✦ ─╮"
echo
echo "What's next:"
echo "  1. Download AI model:"
echo "     ~/.local/share/pixie/models/qwen3-4b-instruct-q4_k_m.gguf"
echo "     (from HuggingFace: unsloth/Qwen3-4B-GGUF)"
echo "  2. Start X:  startx  (or reboot into i3)"
echo "  3. exec zsh  (to see the pink prompt)"
echo "  4. pixie \"hello\"  (test the AI assistant)"
echo "  5. scroll  (browse all commands)"
echo
