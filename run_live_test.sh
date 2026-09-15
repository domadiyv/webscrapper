#!/usr/bin/env bash
# Capture the live portal and audit it. macOS / Linux.
#
#   bash run_live_test.sh
#
# Sets up the venv on first run, then fetches the live portal and audits
# every program it lists. Results land in captures/.

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Creating virtualenv..."
    python3 -m venv .venv
fi

PY=.venv/bin/python

echo "Installing dependencies..."
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt

echo "Ensuring Chromium is installed..."
"$PY" -m playwright install chromium

echo
exec "$PY" scripts/capture_live.py
