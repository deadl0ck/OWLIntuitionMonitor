#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.env"
cd "$SCRIPT_DIR"
/usr/bin/python3 "$SCRIPT_DIR/main.py" > "$SCRIPT_DIR/pumphouse_monitor.log" 2>&1 &
echo "Monitor started (PID: $!)"
