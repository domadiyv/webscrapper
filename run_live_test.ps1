# Capture the live portal and audit it. Windows / PowerShell.
#
#   .\run_live_test.ps1
#
# Sets up the venv on first run, then fetches the live portal and audits
# every program it lists. Results land in captures\.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtualenv..." -ForegroundColor Cyan
    python -m venv .venv
}

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements.txt

Write-Host "Ensuring Chromium is installed..." -ForegroundColor Cyan
& $py -m playwright install chromium

Write-Host ""
& $py scripts\capture_live.py
exit $LASTEXITCODE
