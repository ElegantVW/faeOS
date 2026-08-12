#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
cargo build --release
BIN="$ROOT/target/release/hearth"
echo "built: $BIN"
ls -la "$BIN"
if [[ "${1:-}" == "install" ]]; then
  cp -f "$BIN" "$ROOT/../bin/hearth"
  chmod +x "$ROOT/../bin/hearth"
  mkdir -p "$HOME/bin"
  cp -f "$BIN" "$HOME/bin/hearth"
  chmod +x "$HOME/bin/hearth"
  echo "installed → $HOME/bin/hearth and faeos/bin/hearth"
fi
