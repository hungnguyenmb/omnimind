#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-dev}"
OBFUSCATE="${2:-none}"

if [[ "$OBFUSCATE" != "none" && "$OBFUSCATE" != "pyarmor" ]]; then
  echo "Invalid obfuscation mode: $OBFUSCATE (expected: none|pyarmor)"
  exit 1
fi

python3 scripts/release/build_hardened.py \
  --target macos \
  --version "$VERSION" \
  --obfuscate "$OBFUSCATE" \
  --package zip
