#!/bin/bash
# sync-to-remote.sh — push CodexCrew state from LOCAL → REMOTE Cloud Desktop
# Direction: one-way (local overwrites remote). Run from your laptop/Mac.
# Improvements over sync-codexcrew.sh:
#   - Custom port support (patches config.json after copy)
#   - SQLite WAL sync (memory.db-wal + memory.db-shm)
#   - Session sync for dashboard restore
#   - Full workspace sync (knowledge, scripts, etc.)
#   - --dry-run to preview without transferring
#   - auto_open_browser=false for headless hosts
set -euo pipefail

# --- Defaults ---
DEFAULT_HOST=""
DEFAULT_PORT="7779"

# --- Parse args ---
DRY_RUN=false
HOST=""
PORT=""

usage() {
  cat <<EOF
Usage: sync-to-remote.sh [OPTIONS] [HOST] [PORT]

Push CodexCrew state from LOCAL → REMOTE (one-way, local overwrites remote).
Run this from your laptop/Mac. Patches remote config.json with the specified
port and disables auto_open_browser.

Arguments:
  HOST    Remote hostname (default: $DEFAULT_HOST)
  PORT    Dashboard port on remote (default: $DEFAULT_PORT)

Options:
  -n, --dry-run   Show what would be synced without transferring
  -h, --help      Show this help

Examples:
  sync-to-remote.sh                                          # sync to default host:port
  sync-to-remote.sh remote-host.example.com 7780
  sync-to-remote.sh --dry-run                                # preview only
EOF
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage ;;
    -*) echo "Unknown option: $1" >&2; usage 1 ;;
    *)
      if [[ -z "$HOST" ]]; then HOST="$1"
      elif [[ -z "$PORT" ]]; then PORT="$1"
      else echo "Too many arguments" >&2; usage 1
      fi
      shift ;;
  esac
done

HOST="${HOST:-$DEFAULT_HOST}"
PORT="${PORT:-$DEFAULT_PORT}"

if [[ -z "$HOST" ]]; then
  if $DRY_RUN; then
    HOST="<no-host>"
  else
    echo "Error: no host specified and no default set." >&2
    echo "Edit DEFAULT_HOST in this script or pass hostname as argument." >&2
    exit 1
  fi
fi

# --- Helpers ---
run() {
  if $DRY_RUN; then
    echo "  [dry-run] $*"
  else
    "$@"
  fi
}

rsync_dry() {
  if $DRY_RUN; then
    echo "  [dry-run] rsync $*"
  else
    rsync -az "$@"
  fi
}

echo "=== Syncing CodexCrew to $HOST (port=$PORT) $(${DRY_RUN} && echo '[DRY RUN]') ==="

# --- Create remote dirs ---
if ! $DRY_RUN; then
  ssh "$HOST" "mkdir -p ~/.codex-crew/{workspace/memory,workspace/knowledge,workspace/kb-strategy,workspace/kb-docs,workspace/kiro-agents,workspace/scripts,tasks,skills,hooks,sessions}"
else
  echo "  [dry-run] ssh $HOST mkdir -p ~/.codex-crew/{workspace/...,tasks,skills,hooks,sessions}"
fi

# --- [1] Memory databases (atomic snapshot via .backup) ---
echo "  [1/7] Memory databases (atomic snapshot via .backup)..."
if ! $DRY_RUN; then
  if command -v sqlite3 &>/dev/null; then
    TMP_DB=$(mktemp -t mc-memory-XXXXXX.db)
    trap "rm -f $TMP_DB $TMP_DB-wal $TMP_DB-shm" EXIT
    sqlite3 ~/.codex-crew/memory.db ".backup '$TMP_DB'" || {
      echo "  Warning: sqlite3 .backup failed; falling back to raw copy (may be inconsistent if DB is active)" >&2
      cp ~/.codex-crew/memory.db "$TMP_DB"
    }
    rsync -az "$TMP_DB" "$HOST":~/.codex-crew/memory.db
    # Remove stale WAL/SHM from previous syncs — they'd corrupt the fresh backup
    ssh "$HOST" "rm -f ~/.codex-crew/memory.db-wal ~/.codex-crew/memory.db-shm"
  else
    # Fallback: direct rsync of all DB files (less atomic but works without sqlite3)
    rsync -az ~/.codex-crew/memory.db "$HOST":~/.codex-crew/
    if [ -f ~/.codex-crew/memory.db-wal ]; then
      rsync -az ~/.codex-crew/memory.db-wal "$HOST":~/.codex-crew/
    else
      ssh "$HOST" "rm -f ~/.codex-crew/memory.db-wal"
    fi
    if [ -f ~/.codex-crew/memory.db-shm ]; then
      rsync -az ~/.codex-crew/memory.db-shm "$HOST":~/.codex-crew/
    else
      ssh "$HOST" "rm -f ~/.codex-crew/memory.db-shm"
    fi
  fi
  # memory_index.db is small and not in WAL mode — safe as direct rsync
  if [ -f ~/.codex-crew/memory_index.db ]; then
    rsync -az ~/.codex-crew/memory_index.db "$HOST":~/.codex-crew/
  fi
else
  echo "  [dry-run] sqlite3 .backup → rsync atomic snapshot to $HOST"
  echo "  [dry-run] rsync memory_index.db"
fi

# --- [2] Workspace ---
echo "  [2/7] Workspace..."
if [ -d ~/.codex-crew/workspace/memory/ ]; then
  rsync_dry ~/.codex-crew/workspace/memory/ "$HOST":~/.codex-crew/workspace/memory/
fi
if [ -d ~/.codex-crew/workspace/knowledge/ ]; then
  rsync_dry ~/.codex-crew/workspace/knowledge/ "$HOST":~/.codex-crew/workspace/knowledge/
fi
if [ -d ~/.codex-crew/workspace/kb-strategy/ ]; then
  rsync_dry ~/.codex-crew/workspace/kb-strategy/ "$HOST":~/.codex-crew/workspace/kb-strategy/
fi
if [ -d ~/.codex-crew/workspace/kb-docs/ ]; then
  rsync_dry ~/.codex-crew/workspace/kb-docs/ "$HOST":~/.codex-crew/workspace/kb-docs/
fi
if [ -d ~/.codex-crew/workspace/kiro-agents/ ]; then
  rsync_dry ~/.codex-crew/workspace/kiro-agents/ "$HOST":~/.codex-crew/workspace/kiro-agents/
fi
if [ -d ~/.codex-crew/workspace/scripts/ ]; then
  rsync_dry ~/.codex-crew/workspace/scripts/ "$HOST":~/.codex-crew/workspace/scripts/
fi
rsync_dry ~/.codex-crew/workspace/*.md "$HOST":~/.codex-crew/workspace/ 2>/dev/null || true
rsync_dry ~/.codex-crew/workspace/*.yaml "$HOST":~/.codex-crew/workspace/ 2>/dev/null || true
rsync_dry ~/.codex-crew/workspace/*.json "$HOST":~/.codex-crew/workspace/ 2>/dev/null || true

# --- [3] Config (copy + patch port) ---
echo "  [3/7] Config (port=$PORT, auto_open_browser=false)..."
if ! $DRY_RUN; then
  scp -q ~/.codex-crew/config.json "$HOST":~/.codex-crew/config.json
  ssh "$HOST" python3 - "$PORT" <<'PY'
import json, os, sys
port = sys.argv[1]
p = os.path.expanduser('~/.codex-crew/config.json')
with open(p) as f: cfg = json.load(f)
cfg['dashboard']['url'] = f'http://localhost:{port}'
cfg['dashboard']['auto_open_browser'] = False
with open(p, 'w') as f: json.dump(cfg, f, indent=2)
PY
else
  echo "  [dry-run] scp config.json → patch dashboard.url=http://localhost:$PORT"
fi

# --- [4] Skills, hooks & tasks ---
echo "  [4/7] Skills, hooks & tasks..."
if [ -d ~/.codex-crew/skills/ ]; then
  rsync_dry ~/.codex-crew/skills/ "$HOST":~/.codex-crew/skills/
fi
if [ -d ~/.codex-crew/hooks/ ]; then
  rsync_dry ~/.codex-crew/hooks/ "$HOST":~/.codex-crew/hooks/
fi
if [ -d ~/.codex-crew/tasks/ ]; then
  rsync_dry ~/.codex-crew/tasks/ "$HOST":~/.codex-crew/tasks/
fi

# --- [5] Crons & dashboard metadata ---
# crons.json / hooks.json — runtime state for cron and webhook services.
# folders.json / tags.json / tag_boards.json — sidebar grouping, tag vocabulary,
#   kanban columns. Without folders.json, sessions render flat on the remote
#   because every slot's folder_id points at IDs that don't exist there.
# autonudge.json — autonudge loop state.
echo "  [5/7] Crons & dashboard metadata..."
for f in crons.json hooks.json folders.json tags.json tag_boards.json autonudge.json; do
  if [ -f ~/.codex-crew/"$f" ]; then
    run scp -q ~/.codex-crew/"$f" "$HOST":~/.codex-crew/
  fi
done

# --- [6] Dotfiles ---
echo "  [6/7] Dotfiles (skipped by default)..."
# Uncomment to sync dotfiles — may overwrite remote shell config (shell hooks, SSO aliases)
# run scp -q ~/.gitconfig ~/.bashrc ~/.zshrc "$HOST":~/ 2>/dev/null || true

# --- [7] Sessions ---
echo "  [7/7] Sessions..."
if [ -d ~/.codex-crew/sessions/ ]; then
  rsync_dry ~/.codex-crew/sessions/ "$HOST":~/.codex-crew/sessions/
fi

echo ""
if $DRY_RUN; then
  echo "=== Dry run complete. No files transferred. ==="
  echo "    Remove --dry-run to sync for real."
else
  echo "=== Done. Remote config: port=$PORT, auto_open_browser=false ==="
  echo "    Next: restart gateway on $HOST ('codexcrew gateway &')"
  echo "    Then: ssh -fN -L $PORT:localhost:$PORT $HOST"
fi
