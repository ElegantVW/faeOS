#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
cargo build --release
BIN="$ROOT/target/release/rift"
echo "built: $BIN"
ls -la "$BIN"
if [[ "${1:-}" == "install" ]]; then
  cp -f "$BIN" "$ROOT/../bin/rift"
  chmod +x "$ROOT/../bin/rift"
  mkdir -p "$HOME/bin"
  cp -f "$BIN" "$HOME/bin/rift"
  chmod +x "$HOME/bin/rift"
  echo "installed → $HOME/bin/rift and faeos/bin/rift"
fi
