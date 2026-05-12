#!/usr/bin/env bash
# Manage the YampGM API server (uvicorn on port 8767).
#
# Usage:
#   scripts/api.sh start      — start the server (background, logs to api_server.log)
#   scripts/api.sh stop       — kill the server AND its worker processes
#   scripts/api.sh restart    — stop then start
#   scripts/api.sh status     — show whether the server is running
#   scripts/api.sh clean      — kill any orphaned python worker processes

set -euo pipefail

API_PORT=8767
PID_FILE=".api.pid"
LOG_FILE="api_server.log"

_pid_on_port() {
    # Returns the PID listening on API_PORT, or empty string.
    powershell.exe -NoProfile -Command \
        "(Get-NetTCPConnection -LocalPort $API_PORT -State Listen -ErrorAction SilentlyContinue).OwningProcess" \
        2>/dev/null | tr -d '\r\n'
}

_kill_tree() {
    local pid=$1
    echo "Killing PID $pid and its process tree..."
    # /T kills children (the ProcessPoolExecutor workers) as well as the parent.
    taskkill //PID "$pid" //F //T 2>/dev/null && echo "Done." || echo "Process already gone."
}

cmd_stop() {
    local pid
    pid=$(_pid_on_port)
    if [[ -z "$pid" ]]; then
        echo "No process found on port $API_PORT."
    else
        _kill_tree "$pid"
    fi
    rm -f "$PID_FILE"
}

cmd_start() {
    local pid
    pid=$(_pid_on_port)
    if [[ -n "$pid" ]]; then
        echo "Server already running (PID $pid). Use 'restart' to bounce it."
        exit 1
    fi
    echo "Starting API on port $API_PORT... (logs -> $LOG_FILE)"
    uv run uvicorn gridiron_yampylytics.ffb.api.main:app --port $API_PORT \
        >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 1
    pid=$(_pid_on_port)
    if [[ -n "$pid" ]]; then
        echo "Server up (PID $pid)."
    else
        echo "Server did not start — check $LOG_FILE."
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
        echo "Running (PID $pid) on port $API_PORT."
    else
        echo "Not running."
    fi
}

cmd_clean() {
    echo "Looking for orphaned gridiron_yampylytics worker processes..."
    # Workers show the engine module in their command line when spawned on Windows.
    powershell.exe -NoProfile -Command "
        Get-WmiObject Win32_Process |
        Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -like '*gridiron_yampylytics*' } |
        ForEach-Object { Write-Host \"Killing PID \$(\$_.ProcessId)\"; Stop-Process -Id \$_.ProcessId -Force }
    " 2>/dev/null
    echo "Clean complete."
}

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    clean)   cmd_clean ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|clean}"
        exit 1
        ;;
esac
