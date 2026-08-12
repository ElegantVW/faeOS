#!/usr/bin/env bash
# install.sh — install faeos onto this machine
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BIN_DST="${PIXIE_BIN:-$HOME/bin}"
CFG="$HOME/.config"
PIXIE_CFG="$CFG/pixie"
WITH_LIBS=0
ENABLE_LLM=0
NO_ZSH=0

usage() {
  cat <<EOF
Usage: ./install.sh [options]

  --with-libs     Copy llama.cpp libs from this machine's ~/.local/lib/pixie
                  (or from kit vendor if present). Needed if you don't install
                  system llama-cpp / have a bundled llama-server.
  --enable-llm    systemctl --user enable --now menagerie
  --no-zsh        Don't touch ~/.zshrc
  -h, --help      This help

After install:
  1. Put a GGUF model at:
       ~/.local/share/pixie/models/qwen3-4b-instruct-q4_k_m.gguf
  2. Open a new terminal (or: source ~/.config/pixie/pixie.zsh)
  3. menagerie status all     # or just run any AI app — it summons its own
  4. pixie "hello"
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-libs) WITH_LIBS=1; shift ;;
    --enable-llm) ENABLE_LLM=1; shift ;;
    --no-zsh) NO_ZSH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

echo "==> faeos install from $ROOT"

mkdir -p "$BIN_DST" "$PIXIE_CFG" "$CFG" \
  "$HOME/.local/share/pixie/models" \
  "$HOME/.cache/pixie" \
  "$HOME/.config/systemd/user"

echo "==> bin → $BIN_DST"
cp -a "$ROOT/bin/." "$BIN_DST/"
chmod +x "$BIN_DST"/*

echo "==> configs"
cp -a "$ROOT/config/starship.toml" "$CFG/starship.toml"
cp -a "$ROOT/config/palette.env" "$CFG/palette.env"
cp -a "$ROOT/shell/pixie.zsh" "$PIXIE_CFG/pixie.zsh"
if [[ ! -f "$PIXIE_CFG/tick" ]]; then
  cp -a "$ROOT/config/tick.default" "$PIXIE_CFG/tick"
fi

echo "==> desktop configs"
for dir in kitty i3 picom kmscon rofi dunst; do
  mkdir -p "$CFG/$dir"
  cp -a "$ROOT/config/$dir/." "$CFG/$dir/" 2>/dev/null || true
done
mkdir -p "$CFG/gtk-3.0" "$CFG/gtk-4.0" "$CFG/qt5ct"
cp -a "$ROOT/config/gtk/settings.ini" "$CFG/gtk-3.0/" 2>/dev/null || true
cp -a "$ROOT/config/gtk/settings.ini" "$CFG/gtk-4.0/" 2>/dev/null || true
cp -a "$ROOT/config/qt/qt5ct.conf" "$CFG/qt5ct/" 2>/dev/null || true

echo "==> wallpaper"
mkdir -p "$HOME/Pictures"
cp -a "$ROOT/assets/wall.png" "$HOME/Pictures/" 2>/dev/null || true

echo "==> AI registry (menagerie: models + per-app bindings)"
"$BIN_DST/menagerie-registry.py" seed || true

if (( WITH_LIBS )); then
  echo "==> llama.cpp libs → ~/.local/lib/pixie"
  mkdir -p "$HOME/.local/lib/pixie"
  if [[ -d "$HOME/.local/lib/pixie" && -x "$HOME/.local/lib/pixie/llama-server" ]]; then
    echo "    (already present)"
  elif [[ -d /usr/lib/ollama && -x /usr/lib/ollama/llama-server ]]; then
    # legacy: copy from ollama package if still installed
    cp -a /usr/lib/ollama/*.so* "$HOME/.local/lib/pixie/" 2>/dev/null || true
    cp -f /usr/lib/ollama/llama-server "$HOME/.local/lib/pixie/llama-server"
    chmod +x "$HOME/.local/lib/pixie/llama-server"
  elif command -v llama-server >/dev/null 2>&1; then
    echo "    system llama-server found: $(command -v llama-server)"
  else
    echo "    WARN: no libs found. Install: sudo pacman -S llama-cpp"
    echo "    or copy a working ~/.local/lib/pixie from another machine."
  fi
fi

MARKER="# >>> faeos >>>"
if (( ! NO_ZSH )); then
  ZSHRC="$HOME/.zshrc"
  touch "$ZSHRC"
  if ! grep -qF "$MARKER" "$ZSHRC" 2>/dev/null; then
    echo "==> append source line to ~/.zshrc"
    cat >> "$ZSHRC" <<EOF

$MARKER
# Pixie kit (prompt, tick, play, PATH) — managed by faeos/install.sh
[[ -r "\$HOME/.config/pixie/pixie.zsh" ]] && source "\$HOME/.config/pixie/pixie.zsh"
# <<< faeos <<<
EOF
  else
    echo "==> ~/.zshrc already sources faeos"
  fi
fi

if (( ENABLE_LLM )); then
  echo "==> AI is summoned on demand — no boot service anymore"
  echo "    (each app owns its own llama-server; menagerie manages them)"
  echo "    try:  menagerie status all   or   pixie \"hello\""
fi

MODEL="$HOME/.local/share/pixie/models/qwen3-4b-instruct-q4_k_m.gguf"
echo
echo "Done."
echo "  tools:   $BIN_DST"
echo "  shell:   $PIXIE_CFG/pixie.zsh"
echo "  model:   $MODEL  $([[ -e $MODEL ]] && echo OK || echo MISSING)"
echo
echo "Deps (install via package manager):"
echo "  required: zsh python3 starship"
echo "  agent:    llama-server (llama-cpp) + GGUF model"
echo "  music:    mpv  (+ wpctl for volume on PipeWire)"
echo "  search:   ddgr (duck)"
echo "  optional: aerc (mail), aria2c/curl (ether downloads)"
echo
echo "Reload shell:  exec zsh"
echo "Or:            source ~/.config/pixie/pixie.zsh"
