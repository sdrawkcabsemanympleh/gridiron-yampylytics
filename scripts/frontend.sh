#!/usr/bin/env bash
# Manage the YampGM React/Vite dev server.
#
# Usage:
#   scripts/frontend.sh start    — start Vite dev server (background, logs to frontend_server.log)
#   scripts/frontend.sh stop     — stop the dev server
#   scripts/frontend.sh restart  — stop then start
#   scripts/frontend.sh status   — show whether the server is running

set -euo pipefail

VITE_PORT=5173
PID_FILE=".frontend.pid"
LOG_FILE="frontend_server.log"
FRONTEND_DIR="frontend"

_pid_on_port() {
    powershell.exe -NoProfile -Command \
        "(Get-NetTCPConnection -LocalPort $VITE_PORT -State Listen -ErrorAction SilentlyContinue).OwningProcess" \
        2>/dev/null | tr -d '\r\n'
}

cmd_stop() {
    local pid
    pid=$(_pid_on_port)
    if [[ -z "$pid" ]]; then
        echo "No process found on port $VITE_PORT."
    else
        echo "Killing PID $pid..."
        taskkill //PID "$pid" //F //T 2>/dev/null && echo "Done." || echo "Process already gone."
    fi
    rm -f "$PID_FILE"
}

cmd_start() {
    local pid
    pid=$(_pid_on_port)
    if [[ -n "$pid" ]]; then
        echo "Dev server already running (PID $pid). Use 'restart' to bounce it."
        exit 1
    fi
    echo "Starting Vite dev server on port $VITE_PORT... (logs -> $LOG_FILE)"
    (cd "$FRONTEND_DIR" && npm run dev >> "../$LOG_FILE" 2>&1) &
    echo $! > "$PID_FILE"
    sleep 2
    pid=$(_pid_on_port)
    if [[ -n "$pid" ]]; then
        echo "Dev server up (PID $pid) — http://localhost:$VITE_PORT"
    else
        echo "Dev server did not start — check $LOG_FILE."
        exit 1
    fi
}

cmd_restart() {
    cmd_stop || true
    sleep 1
    cmd_start
}

cmd_status() {
    local pid
    pid=$(_pid_on_port)
    if [[ -n "$pid" ]]; then
        echo "Running (PID $pid) on port $VITE_PORT — http://localhost:$VITE_PORT"
    else
        echo "Not running."
    fi
}

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
