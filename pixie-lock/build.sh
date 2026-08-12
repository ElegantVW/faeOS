#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
cargo build --release
BIN="$ROOT/target/release/pixie-lock"
echo "built: $BIN"
ls -la "$BIN"
if [[ "${1:-}" == "install" ]]; then
  cp -f "$BIN" "$ROOT/../bin/pixie-lock"
  chmod +x "$ROOT/../bin/pixie-lock"
  mkdir -p "$HOME/bin"
  cp -f "$BIN" "$HOME/bin/pixie-lock"
  chmod +x "$HOME/bin/pixie-lock"
  echo "installed → $HOME/bin/pixie-lock and faeos/bin/pixie-lock"
fi
