#!/usr/bin/env bash
# hearth — build + install into faeOS engine paths (never commit ELFs)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
cargo build --release
BIN="$ROOT/target/release/hearth"
echo "built: $BIN"
ls -la "$BIN"
if [[ "${1:-}" == "install" ]]; then
  LIB="$HOME/.local/lib/faeos"
  mkdir -p "$LIB" "$HOME/bin"
  cp -f "$BIN" "$LIB/hearth"
  chmod +x "$LIB/hearth"
  WRAP="$ROOT/../bin/hearth"
  if [[ -f "$WRAP" ]]; then
    if [[ ! -e "$HOME/bin/hearth" ]] || file -b "$HOME/bin/hearth" 2>/dev/null | grep -q ELF; then
      cp -f "$WRAP" "$HOME/bin/hearth"
      chmod +x "$HOME/bin/hearth"
    fi
  fi
  echo "installed engine → $LIB/hearth"
fi
