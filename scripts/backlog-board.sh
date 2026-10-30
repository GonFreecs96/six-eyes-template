#!/usr/bin/env bash
set -euo pipefail

# Backlog Board — local Flask server launcher
# Supports: start, stop, status

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$REPO_ROOT/data/state/backlog-board.pid"
LOG_FILE="$REPO_ROOT/data/state/backlog-board.log"
BACKLOG_BOARD_PORT="${BACKLOG_BOARD_PORT:-5151}"

# Helper: check if process is running
is_running() {
  [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

# Helper: get current PID
get_pid() {
  [ -f "$PID_FILE" ] && cat "$PID_FILE"
}

case "${1:-}" in
  start)
    if is_running; then
      PID=$(get_pid)
      echo "Already running (PID $PID) — http://127.0.0.1:${BACKLOG_BOARD_PORT}"
      exit 0
    fi

    # Check if flask and markdown are importable
    if ! "$REPO_ROOT/.venv/bin/python3" -c "import flask, markdown" 2>/dev/null; then
      echo "Installing dependencies..."
      "$REPO_ROOT/.venv/bin/python3" -m pip install -r "$REPO_ROOT/requirements.txt"
    fi

    # Launch in background
    nohup "$REPO_ROOT/.venv/bin/python3" "$REPO_ROOT/webapp/backlog_board/app.py" > "$LOG_FILE" 2>&1 &
    NEW_PID=$!
    echo "$NEW_PID" > "$PID_FILE"

    # Wait for it to start
    sleep 1

    echo "Started (PID $NEW_PID) — http://127.0.0.1:${BACKLOG_BOARD_PORT}"
    exit 0
    ;;

  stop)
    if [ ! -f "$PID_FILE" ]; then
      echo "Not running."
      exit 0
    fi

    PID=$(cat "$PID_FILE")
    if kill "$PID" 2>/dev/null; then
      rm -f "$PID_FILE"
      echo "Stopped."
    else
      rm -f "$PID_FILE"
      echo "Stopped."
    fi
    exit 0
    ;;

  status)
    if is_running; then
      PID=$(get_pid)
      echo "Running (PID $PID) — http://127.0.0.1:${BACKLOG_BOARD_PORT}"
      exit 0
    else
      echo "Not running."
      exit 0
    fi
    ;;

  *)
    echo "Usage: backlog-board.sh {start|stop|status}"
    exit 1
    ;;
esac
