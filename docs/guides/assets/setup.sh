#!/bin/bash
# Codex Crew Persistent Sessions Setup
#
# Installs codexcrew gateway as a systemd user service.
# Requires the systemd user manager to be running (see README.md Phase 1).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USERNAME=$(whoami)
HOSTNAME=$(hostname)

echo ">_ Codex Crew Persistent Sessions Setup"
echo ""

# ── Check: systemd user manager running? ──
if ! systemctl --user status >/dev/null 2>&1; then
    echo "❌ Systemd user manager is not running."
    echo "   Complete Phase 1 in README.md first (requires sudo, one-time)."
    exit 1
fi
echo "✅ Systemd user manager running"

# ── Check: codexcrew gateway already running in tmux? ──
if pgrep -f "codex_crew gateway\|codexcrew gateway" | grep -v $$ >/dev/null 2>&1; then
    echo ""
    echo "⚠️  codexcrew gateway is already running (tmux or manual)."
    echo "   Kill it first: tmux kill-session -t codexcrew"
    echo "   Then re-run this script."
    exit 1
fi

# ── Install user service ──
echo "→ Installing codexcrew user service..."
USER_UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_UNIT_DIR"
NODE_VERSION=$(node --version 2>/dev/null || basename "$(ls -d "$HOME"/.nvm/versions/node/v* 2>/dev/null | tail -1)")

# Resolve codexcrew binary from current shell PATH
CODEXCREW_BIN="$(command -v codexcrew 2>/dev/null)" || { echo "❌ codexcrew not found in PATH"; exit 1; }
echo "  Binary: $CODEXCREW_BIN"

sed -e "s/%u/$USERNAME/g" \
    -e "s|CODEXCREW_BIN|$CODEXCREW_BIN|g" \
    -e "s/NVM_NODE_VERSION/$NODE_VERSION/g" \
    "$SCRIPT_DIR/codexcrew.service" > "$USER_UNIT_DIR/codexcrew.service"

systemctl --user daemon-reload
systemctl --user enable codexcrew
systemctl --user start codexcrew

echo ""
systemctl --user status codexcrew --no-pager || true

# ── Mac instructions ──
echo ""
echo "━━━ Mac Setup (run on your laptop) ━━━"
echo ""
echo "scp $USERNAME@$HOSTNAME:$SCRIPT_DIR/com.codexcrew.tunnel.plist ~/Library/LaunchAgents/"
echo "sed -i '' 's|ALIAS@DEV_DESKTOP_HOSTNAME|$USERNAME@$HOSTNAME|g' ~/Library/LaunchAgents/com.codexcrew.tunnel.plist"
echo "launchctl load ~/Library/LaunchAgents/com.codexcrew.tunnel.plist"
echo ""
echo "Done! Dashboard: http://localhost:5486"
