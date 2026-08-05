#!/usr/bin/env bash
# build.sh — produce release bulwark binary (builder machine only)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
cargo build --release
BIN="$ROOT/target/release/bulwark"
echo "built: $BIN"
ls -la "$BIN"
# optional install into faeos kit + ~/bin
if [[ "${1:-}" == "install" ]]; then
  cp -f "$BIN" "$ROOT/../bin/bulwark-bin"
  cp -f "$ROOT/../bin/bulwark-wrap" "$ROOT/../bin/bulwark" 2>/dev/null || true
  # prefer real binary as bin/bulwark
  cp -f "$BIN" "$ROOT/../bin/bulwark"
  chmod +x "$ROOT/../bin/bulwark"
  mkdir -p "$HOME/bin"
  cp -f "$BIN" "$HOME/bin/bulwark"
  chmod +x "$HOME/bin/bulwark"
  echo "installed → $HOME/bin/bulwark and faeos/bin/bulwark"
fi
