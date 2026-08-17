#!/usr/bin/env bash
# install.sh — install faeos onto this machine (source-only kit + optional builds)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BIN_DST="${PIXIE_BIN:-$HOME/bin}"
CFG="$HOME/.config"
PIXIE_CFG="$CFG/pixie"
WITH_LIBS=0
ENABLE_LLM=0
NO_ZSH=0
DO_BUILD=0
DO_BUILD_ENGINES=0

usage() {
  cat <<EOF
Usage: ./install.sh [options]

  --with-libs       Copy llama.cpp libs from this machine's ~/.local/lib/pixie
                    (or from kit vendor if present). Needed if you don't install
                    system llama-cpp / have a bundled llama-server.
  --build           Build in-tree Rust engines (seal, hearth, rift) if present
  --build-engines   If ~/bulwark or ~/fairy-lantern exist, run their build.sh install
  --enable-llm      Hint for on-demand AI (menagerie) — no boot service
  --no-zsh          Don't touch ~/.zshrc
  -h, --help        This help

Source-only: git never ships prebuilt ELFs. Launchers live in bin/; engines
install to ~/.local/lib/faeos/. See docs/engines.md.

After install:
  1. Optional engines:
       git clone git@github.com:ElegantVW/bulwark.git ~/bulwark
       cd ~/bulwark && ./build.sh install
       git clone git@github.com:ElegantVW/fairy-lantern.git ~/fairy-lantern
       cd ~/fairy-lantern && ./build.sh install
  2. Put a GGUF model at:
       ~/.local/share/pixie/models/qwen3-4b-instruct-q4_k_m.gguf
  3. Open a new terminal (or: source ~/.config/pixie/pixie.zsh)
  4. menagerie status all     # or just run any AI app — it summons its own
  5. pixie "hello"
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-libs) WITH_LIBS=1; shift ;;
    --build) DO_BUILD=1; shift ;;
    --build-engines) DO_BUILD_ENGINES=1; shift ;;
    --enable-llm) ENABLE_LLM=1; shift ;;
    --no-zsh) NO_ZSH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

echo "==> faeos install from $ROOT"

mkdir -p "$BIN_DST" "$PIXIE_CFG" "$CFG" \
  "$HOME/.local/share/pixie/models" \
  "$HOME/.local/lib/faeos" \
  "$HOME/.cache/pixie" \
  "$HOME/.config/systemd/user"

echo "==> bin (scripts + launchers only) → $BIN_DST"
cp -a "$ROOT/bin/." "$BIN_DST/"
# Never leave a prebuilt ELF as the public command if a launcher exists in kit
for eng in seal hearth rift bulwark fairy fairy-lantern; do
  kit="$ROOT/bin/$eng"
  dst="$BIN_DST/$eng"
  if [[ -f "$kit" ]] && file -b "$kit" 2>/dev/null | grep -qv ELF; then
    cp -f "$kit" "$dst"
  fi
done
chmod +x "$BIN_DST"/* 2>/dev/null || true

echo "==> configs"
cp -a "$ROOT/config/starship.toml" "$CFG/starship.toml"
cp -a "$ROOT/config/palette.env" "$CFG/palette.env"
cp -a "$ROOT/shell/pixie.zsh" "$PIXIE_CFG/pixie.zsh"
if [[ ! -f "$PIXIE_CFG/tick" ]]; then
  cp -a "$ROOT/config/tick.default" "$PIXIE_CFG/tick"
fi
if [[ ! -f "$PIXIE_CFG/seal.json" ]]; then
  cp -a "$ROOT/config/seal.default.json" "$PIXIE_CFG/seal.json"
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

echo "==> systemd user units"
cp -a "$ROOT/systemd/." "$HOME/.config/systemd/user/" 2>/dev/null || true

echo "==> AI registry (menagerie: models + per-app bindings)"
"$BIN_DST/menagerie-registry.py" seed || true

if (( WITH_LIBS )); then
  echo "==> llama.cpp libs → ~/.local/lib/pixie"
  mkdir -p "$HOME/.local/lib/pixie"
  if [[ -x "$HOME/.local/lib/pixie/llama-server" ]]; then
    echo "    (already present)"
  elif [[ -d /usr/lib/ollama && -x /usr/lib/ollama/llama-server ]]; then
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

if (( DO_BUILD )); then
  echo "==> build in-tree engines (seal / hearth / rift)"
  if ! command -v cargo >/dev/null 2>&1; then
    echo "    WARN: cargo not found — skip --build" >&2
  else
    for crate in seal hearth rift; do
      if [[ -x "$ROOT/$crate/build.sh" ]]; then
        echo "    → $crate"
        "$ROOT/$crate/build.sh" install || echo "    WARN: $crate build failed" >&2
      fi
    done
  fi
fi

if (( DO_BUILD_ENGINES )); then
  echo "==> build sibling engines if present"
  if ! command -v cargo >/dev/null 2>&1; then
    echo "    WARN: cargo not found — skip --build-engines" >&2
  else
    if [[ -x "$HOME/bulwark/build.sh" ]]; then
      echo "    → bulwark"
      "$HOME/bulwark/build.sh" install || echo "    WARN: bulwark build failed" >&2
    else
      echo "    (no ~/bulwark — clone ElegantVW/bulwark to enable)"
    fi
    if [[ -x "$HOME/fairy-lantern/build.sh" ]]; then
      echo "    → fairy-lantern"
      "$HOME/fairy-lantern/build.sh" install || echo "    WARN: fairy-lantern build failed" >&2
    else
      echo "    (no ~/fairy-lantern — clone ElegantVW/fairy-lantern to enable)"
    fi
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
echo "  engines: $HOME/.local/lib/faeos  (build with --build / --build-engines)"
echo "  shell:   $PIXIE_CFG/pixie.zsh"
echo "  model:   $MODEL  $([[ -e $MODEL ]] && echo OK || echo MISSING)"
echo
echo "Optional engines (plug-and-play — see docs/engines.md):"
if [[ -x "$HOME/.local/lib/faeos/bulwark" ]]; then
  echo "  bulwark:       OK"
else
  echo "  bulwark:       missing — git clone …/bulwark.git ~/bulwark && ./build.sh install"
fi
if [[ -x "$HOME/.local/lib/faeos/fairy" ]]; then
  echo "  fairy-lantern: OK"
else
  echo "  fairy-lantern: missing — git clone …/fairy-lantern.git ~/fairy-lantern && ./build.sh install"
fi
echo
echo "Deps (install via package manager):"
echo "  required: zsh python3 starship"
echo "  agent:    llama-server (llama-cpp) + GGUF model"
echo "  music:    mpv  (+ wpctl for volume on PipeWire)"
echo "  search:   ddgr (duck)"
echo "  rust:     cargo (for --build / external engines)"
echo "  optional: aerc (mail), aria2c/curl (ether downloads)"
echo
echo "Reload shell:  exec zsh"
echo "Or:            source ~/.config/pixie/pixie.zsh"
