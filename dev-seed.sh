#!/bin/bash
# Copy the CodexCrew data home into .codexcrew-dev/ for local development.
# Safe to re-run — wipes .codexcrew-dev first so you get a clean snapshot.
#
# Usage: ./dev-seed.sh
set -e

# The data home moved from the top-level ~/.codexcrew to ~/.codex-crew. Prefer
# the current location; fall back to the legacy one for a box that still uses
# it so this script doesn't silently no-op.
if [ -d "$HOME/.codex-crew" ]; then
  SRC="$HOME/.codex-crew"
elif [ -d "$HOME/.codexcrew" ]; then
  SRC="$HOME/.codexcrew"
else
  SRC=""
fi
DST="$(cd "$(dirname "$0")" && pwd)/.codexcrew-dev"

if [ -z "$SRC" ]; then
  echo "No ~/.codex-crew or ~/.codexcrew found — nothing to seed."
  exit 0
fi

if [ -d "$DST" ]; then
  # Refuse to rm -rf if .codexcrew-dev is a symlink (could follow to unrelated dir)
  if [ -L "$DST" ]; then
    echo "ERROR: .codexcrew-dev is a symlink — refusing to remove. Delete it manually."
    exit 1
  fi
  echo "Removing existing .codexcrew-dev/ ..."
  rm -rf "$DST"
fi

echo "Copying $SRC → .codexcrew-dev/ ..."
cp -R "$SRC" "$DST"

echo "Done. Start the gateway with:"
echo "  CODEXCREW_HOME=.codexcrew-dev bin/codexcrew gateway"
