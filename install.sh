#!/usr/bin/env bash
# Installs the seo-scan skill into your Claude Code skills directory (macOS/Linux).
#   User-wide:    bash install.sh
#   Project-only: bash install.sh --project
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/skills/seo-scan"

if [ "${1:-}" = "--project" ]; then
  DEST="$(pwd)/.claude/skills/seo-scan"
else
  DEST="${HOME}/.claude/skills/seo-scan"
fi

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$SRC" "$DEST"

echo "Installed seo-scan skill to $DEST"
echo "Optional extras: pip install -r \"$DEST/requirements.txt\""
