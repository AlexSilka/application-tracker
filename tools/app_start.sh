#!/bin/bash
# tools/app_start.sh — start (or restart) the Application Tracker.
#
# Brings up two DETACHED servers that keep running after this terminal is
# closed: the FastAPI backend on :8787 and the Vite dev server on :5173
# (which proxies /api -> :8787). Re-running restarts cleanly — any previous
# instance is stopped first. Stop everything with tools/app_stop.sh.
#
# Detachment uses nohup + </dev/null + disown, the same POSIX recipe as
# spike_bot/tools/bot_start.sh: ignore the terminal-close SIGHUP, keep stdin
# off the tty, and drop the jobs from this shell's table so bash exiting on
# close can't HUP them either.

set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"

API_PORT=8787          # FastAPI (tracker serve) default
WEB_PORT=5173          # Vite dev server; proxies /api -> API_PORT

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [app_start] $*"; }

# Find our running processes by their absolute argv paths: the backend venv
# entry point, and anything under the frontend's node_modules (covers both the
# Vite process and the esbuild child it spawns). Scoped to THIS checkout, so a
# tracker in another folder is never touched. The `/awk/` guard skips awk's own
# line — its arguments contain the very substrings we match on.
find_pids() {
    ps -axo pid,command | awk \
        -v be="$ROOT/backend/.venv/bin/tracker" \
        -v fe="$ROOT/frontend/node_modules" '
        /awk/ || /app_start\.sh/ || /app_stop\.sh/ { next }
        (index($0, be) > 0) || (index($0, fe) > 0) { print $1 }
    ' | sort -un | tr '\n' ' ' | xargs
}

# --- first-run setup (each block is skipped once its target exists) --------
if [ ! -x "$ROOT/backend/.venv/bin/tracker" ]; then
    log "creating backend venv and installing tracker…"
    python3 -m venv "$ROOT/backend/.venv"
    "$ROOT/backend/.venv/bin/pip" install -q -e "$ROOT/backend"
fi
if [ ! -f "$ROOT/backend/tracker.db" ]; then
    log "seeding sample data…"
    ( cd "$ROOT/backend" && .venv/bin/tracker seed )
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
    log "installing frontend dependencies…"
    ( cd "$ROOT/frontend" && npm install )
fi

# --- restart semantics: stop any previous instance first -------------------
OLD=$(find_pids)
if [ -n "$OLD" ]; then
    log "stopping previous instance: $OLD"
    for pid in $OLD; do kill -TERM "$pid" 2>/dev/null || true; done
    for _ in $(seq 1 20); do
        still=""
        for pid in $OLD; do
            if kill -0 "$pid" 2>/dev/null; then still="$still $pid"; fi
        done
        if [ -z "$still" ]; then break; fi
        sleep 0.25
    done
    for pid in $OLD; do kill -9 "$pid" 2>/dev/null || true; done
    sleep 0.5
fi

# --- launch, detached ------------------------------------------------------
# Invoke by ABSOLUTE path so the argv carries the repo path (that is what
# app_stop.sh / find_pids match on). Each server is cd'd into its own dir
# first: Vite resolves its config from the cwd, and the backend keeps the
# conventional working directory.
printf '\n=== app_start %s ===\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BACKEND_LOG"
printf '\n=== app_start %s ===\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$FRONTEND_LOG"

log "starting API  → http://127.0.0.1:$API_PORT"
cd "$ROOT/backend"
nohup "$ROOT/backend/.venv/bin/tracker" serve --host 127.0.0.1 --port "$API_PORT" \
    >> "$BACKEND_LOG" 2>&1 < /dev/null &
disown 2>/dev/null || true

log "starting web  → http://localhost:$WEB_PORT"
cd "$ROOT/frontend"
nohup "$ROOT/frontend/node_modules/.bin/vite" \
    >> "$FRONTEND_LOG" 2>&1 < /dev/null &
disown 2>/dev/null || true
cd "$ROOT"

# --- wait until each answers (bound, not merely spawned) -------------------
wait_up() {  # $1=url
    for _ in $(seq 1 60); do
        if curl -sf -o /dev/null -m 1 "$1"; then return 0; fi
        sleep 0.5
    done
    return 1
}

if wait_up "http://127.0.0.1:$API_PORT/api/meta"; then
    log "✅ API up"
else
    log "❌ API did not come up in ~30s — see $BACKEND_LOG"; exit 1
fi
if wait_up "http://127.0.0.1:$WEB_PORT/"; then
    log "✅ web up"
else
    log "❌ web did not come up in ~30s — see $FRONTEND_LOG"; exit 1
fi

log "ready → open http://localhost:$WEB_PORT    (stop: tools/app_stop.sh)"
