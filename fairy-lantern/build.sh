#!/usr/bin/env bash
# build.sh — release Fairy Lantern
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
cargo build --release
BIN="$ROOT/target/release/fairy-lantern"
echo "built: $BIN"
ls -la "$BIN"
if [[ "${1:-}" == "install" ]]; then
  mkdir -p "$ROOT/../bin" "$HOME/bin"
  cp -f "$BIN" "$ROOT/../bin/fairy-lantern"
  cp -f "$BIN" "$HOME/bin/fairy-lantern"
  chmod +x "$ROOT/../bin/fairy-lantern" "$HOME/bin/fairy-lantern"
  echo "installed → $HOME/bin/fairy-lantern and faeos/bin/fairy-lantern"
fi
