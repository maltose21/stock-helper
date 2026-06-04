#!/bin/bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
cd "$SKILL_DIR"

log() { echo "[$(date '+%F %T')] $*"; }
log "=== morning_run begin ==="

# Skip weekends
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    log "Weekend, skip"
    exit 0
fi

# Use caffeinate to prevent sleep during execution
caffeinate -i python3 "$SCRIPT_DIR/daily_advice.py"
RC=$?

if [ $RC -eq 0 ]; then
    log "morning advice generated"
else
    log "daily_advice.py failed (exit=$RC)"
    exit 1
fi

log "=== morning_run end ==="
