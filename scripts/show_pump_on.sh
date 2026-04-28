#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sqlite3 "$SCRIPT_DIR/../pumphouse.db" ".read $SCRIPT_DIR/../sql/pump_on.sql"
