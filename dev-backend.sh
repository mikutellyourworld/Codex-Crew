#!/bin/bash
# Run the CodexCrew gateway from LIVE source. Uses the venv Python (which has
# all deps) but PYTHONPATH=src so code changes are picked up immediately on
# restart.
#
# Usage: ./dev-backend.sh
#   - Runs on port 6777 (dev port, separate from production on 5486)
#   - Uses .codexcrew-dev/ as data directory (isolated from ~/.codex-crew/)
#   - Ctrl+C to stop, re-run to pick up changes
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Find the Python with deps installed: prefer the venv created by install.sh /
# setup.sh / minimal_install.sh. Override with RUNTIME_PYTHON if needed.
RUNTIME_PYTHON="${RUNTIME_PYTHON:-}"
if [ -z "$RUNTIME_PYTHON" ] || [ ! -x "$RUNTIME_PYTHON" ]; then
    if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
        RUNTIME_PYTHON="$SCRIPT_DIR/.venv/bin/python"
    fi
fi
if [ ! -x "$RUNTIME_PYTHON" ]; then
    echo "ERROR: Cannot find the CodexCrew venv Python at $SCRIPT_DIR/.venv/bin/python."
    echo "Run 'bash minimal_install.sh' once to set up the venv, then try again."
    exit 1
fi

export PYTHONPATH="$SCRIPT_DIR/src"
export CODEXCREW_HOME="${CODEXCREW_HOME:-.codexcrew-dev}"
# Absolutize: config_dir() resolves this against each process's CWD, and MCP
# subprocesses (mcp-core/mcp-cron) are spawned with session-workspace CWDs —
# a relative HOME makes them create empty config dirs with no .local_secret,
# so their gateway IPC calls fail with 403 Forbidden.
case "$CODEXCREW_HOME" in
    /*) ;;
    *) CODEXCREW_HOME="$SCRIPT_DIR/$CODEXCREW_HOME" ;;
esac
export CODEXCREW_PORT="${CODEXCREW_PORT:-6777}"
export CODEXCREW_PROJECT_DIR="$SCRIPT_DIR"

echo ">_ Dev backend starting (live source, port $CODEXCREW_PORT)"
echo "   Python: $RUNTIME_PYTHON"
echo "   Source: $PYTHONPATH"
echo "   Data:   $CODEXCREW_HOME"
echo ""

exec "$RUNTIME_PYTHON" -m codex_crew gateway "$@"
