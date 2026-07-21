#!/bin/bash
# tools/app_stop.sh — stop the Application Tracker started by app_start.sh.
#
# Sends SIGTERM to the backend, the Vite server and its esbuild child, waits
# up to 10s for a clean exit, then SIGKILLs any survivor. Mirrors
# spike_bot/tools/bot_stop.sh.

set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [app_stop] $*"; }

# Same discovery as app_start.sh: match our processes by their absolute argv
# paths, scoped to this checkout. `/awk/` skips awk's own line (its arguments
# contain the substrings we match on).
find_pids() {
    ps -axo pid,command | awk \
        -v be="$ROOT/backend/.venv/bin/tracker" \
        -v fe="$ROOT/frontend/node_modules" '
        /awk/ || /app_start\.sh/ || /app_stop\.sh/ { next }
        (index($0, be) > 0) || (index($0, fe) > 0) { print $1 }
    ' | sort -un | tr '\n' ' ' | xargs
}

PIDS=$(find_pids)
if [ -z "$PIDS" ]; then
    log "nothing running"
    exit 0
fi

log "SIGTERM → $PIDS"
for pid in $PIDS; do
    kill -TERM "$pid" 2>/dev/null && log "  TERM $pid" || log "  TERM $pid (already gone)"
done

for i in $(seq 1 40); do
    alive=""
    for pid in $PIDS; do
        if kill -0 "$pid" 2>/dev/null; then alive="$alive $pid"; fi
    done
    if [ -z "$alive" ]; then
        log "all stopped after $((i * 250))ms"
        exit 0
    fi
    sleep 0.25
done

log "still alive:$alive — SIGKILL"
for pid in $alive; do kill -9 "$pid" 2>/dev/null || true; done
sleep 0.5
log "done"
