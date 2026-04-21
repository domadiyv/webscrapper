#!/usr/bin/env bash
# One-time setup: creates a virtualenv, installs dependencies,
# installs Playwright browsers, and registers the 9 PM cron job.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

echo "=== Step 1: Creating Python virtual environment ==="
python3 -m venv "$VENV"
source "$VENV/bin/activate"

echo "=== Step 2: Installing Python dependencies ==="
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q

echo "=== Step 3: Installing Playwright browser (Chromium) ==="
playwright install chromium
playwright install-deps chromium

echo "=== Step 4: Making scripts executable ==="
chmod +x "$SCRIPT_DIR/run.sh"

if [ ! -f "$SCRIPT_DIR/.env" ] && [ -f "$SCRIPT_DIR/.env.example" ]; then
    echo "No .env found. Copy .env.example to .env and fill in SMTP credentials to enable email."
fi

echo "=== Step 5: Registering cron job (daily 9 PM) ==="
CRON_LINE="0 21 * * * $SCRIPT_DIR/run.sh >> $SCRIPT_DIR/logs/cron.log 2>&1"

# Add only if not already present
if crontab -l 2>/dev/null | grep -qF "$SCRIPT_DIR/run.sh"; then
    echo "Cron job already registered — skipping."
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "Cron job registered: $CRON_LINE"
fi

echo ""
echo "=== Setup complete! ==="
echo ""
echo "  Run manually anytime:  $SCRIPT_DIR/run.sh"
echo "  Output files:          $SCRIPT_DIR/output/"
echo "  Cron logs:             $SCRIPT_DIR/logs/"
echo ""
echo "Cron schedule: every day at 9:00 PM (server local time)"
crontab -l | grep "$SCRIPT_DIR/run.sh" || true
