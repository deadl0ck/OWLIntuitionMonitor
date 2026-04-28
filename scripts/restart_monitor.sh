#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "Error: .env file not found at $ROOT_DIR/.env — copy .env.example and fill in your values"
    exit 1
fi
pkill -f "python3.*main.py" 2>/dev/null
source "$ROOT_DIR/.env"
cd "$ROOT_DIR"
/usr/bin/python3 "$ROOT_DIR/main.py" > "$ROOT_DIR/pumphouse_monitor.log" 2>&1 &
echo "Monitor restarted (PID: $!)"
