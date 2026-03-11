#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-dev}"
OBFUSCATE="${2:-none}"
PYTHON_BIN="${PYTHON_BIN:-./.venv-build/bin/python}"

if [[ "$OBFUSCATE" != "none" && "$OBFUSCATE" != "pyarmor" ]]; then
  echo "Invalid obfuscation mode: $OBFUSCATE (expected: none|pyarmor)"
  exit 1
fi

"$PYTHON_BIN" scripts/release/build_hardened.py \
  --target macos \
  --version "$VERSION" \
  --obfuscate "$OBFUSCATE" \
  --package zip
