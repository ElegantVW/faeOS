#!/usr/bin/env bash
# seal — build + install into faeOS engine paths (never commit ELFs)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
cargo build --release
BIN="$ROOT/target/release/seal"
echo "built: $BIN"
ls -la "$BIN"
if [[ "${1:-}" == "install" ]]; then
  LIB="$HOME/.local/lib/faeos"
  mkdir -p "$LIB" "$HOME/bin"
  cp -f "$BIN" "$LIB/seal"
  chmod +x "$LIB/seal"
  WRAP="$ROOT/../bin/seal"
  if [[ -f "$WRAP" ]]; then
    if [[ ! -e "$HOME/bin/seal" ]] || file -b "$HOME/bin/seal" 2>/dev/null | grep -q ELF; then
      cp -f "$WRAP" "$HOME/bin/seal"
      chmod +x "$HOME/bin/seal"
    fi
  fi
  echo "installed engine → $LIB/seal"
fi
