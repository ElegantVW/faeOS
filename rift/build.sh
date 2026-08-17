#!/usr/bin/env bash
# rift — build + install into faeOS engine paths (never commit ELFs)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
cargo build --release
BIN="$ROOT/target/release/rift"
echo "built: $BIN"
ls -la "$BIN"
if [[ "${1:-}" == "install" ]]; then
  LIB="$HOME/.local/lib/faeos"
  mkdir -p "$LIB" "$HOME/bin"
  cp -f "$BIN" "$LIB/rift"
  chmod +x "$LIB/rift"
  WRAP="$ROOT/../bin/rift"
  if [[ -f "$WRAP" ]]; then
    if [[ ! -e "$HOME/bin/rift" ]] || file -b "$HOME/bin/rift" 2>/dev/null | grep -q ELF; then
      cp -f "$WRAP" "$HOME/bin/rift"
      chmod +x "$HOME/bin/rift"
    fi
  fi
  echo "installed engine → $LIB/rift"
fi
