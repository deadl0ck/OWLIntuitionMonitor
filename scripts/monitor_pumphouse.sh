#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
source "$ROOT_DIR/.env"
cd "$ROOT_DIR"
/usr/bin/python3 "$ROOT_DIR/main.py" > "$ROOT_DIR/pumphouse_monitor.log" 2>&1 &
echo "Monitor started (PID: $!)"
