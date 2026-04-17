#!/usr/bin/env bash
# Daily wrapper executed by cron at 9 PM.
# Activates the virtual environment and runs the scraper.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/scraper_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"

echo "[$(date)] Starting RecDesk scraper" | tee -a "$LOG_FILE"

# Activate virtual environment
source "$VENV/bin/activate"

# Run scraper; tee output to log
python "$SCRIPT_DIR/scraper.py" 2>&1 | tee -a "$LOG_FILE"

echo "[$(date)] Scraper finished. Output in $SCRIPT_DIR/output/" | tee -a "$LOG_FILE"
