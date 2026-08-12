#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
cargo build --release
BIN="$ROOT/target/release/seal"
echo "built: $BIN"
ls -la "$BIN"
if [[ "${1:-}" == "install" ]]; then
  cp -f "$BIN" "$ROOT/../bin/seal"
  chmod +x "$ROOT/../bin/seal"
  mkdir -p "$HOME/bin"
  cp -f "$BIN" "$HOME/bin/seal"
  chmod +x "$HOME/bin/seal"
  echo "installed → $HOME/bin/seal and faeos/bin/seal"
fi
