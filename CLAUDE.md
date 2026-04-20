# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Running

```bash
# One-time setup (creates venv, installs deps, registers 9 PM cron job)
bash setup.sh

# Run scraper manually
source .venv/bin/activate
python scraper.py

# Run via cron wrapper (logs to logs/scraper_YYYYMMDD_HHMMSS.log)
bash run.sh
```

## Dependencies

Python 3 + venv at `.venv/`. Install with:
```bash
pip install -r requirements.txt
playwright install chromium
playwright install-deps
```

No tests exist in this project.

## Architecture

Single-file scraper (`scraper.py`) targeting RecDesk community programs at `jcrec.recdesk.com`, filtered to age 8 (`TARGET_AGE = 8`). Output goes to `output/programs_age8_YYYYMMDD_HHMMSS.xlsx`.

**Two-stage scraping strategy** (preferred → fallback):
1. **API interception** — Playwright intercepts XHR/fetch responses and parses JSON if the page makes API calls
2. **DOM scraping** — Falls back to parsing table rows/cards with pagination support

**Key functions:**
- `age_includes(age_range_str, target)` — Parses many age formats ("6-9", "8+", "8 and up", etc.)
- `extract_row_data(row)` — Extracts program fields from a DOM row element
- `_parse_api_programs(data)` — Normalizes JSON API responses (handles multiple field name variants)
- `scrape()` — Async entry point; drives Playwright Chromium, handles pagination and timeouts
- `save_excel(programs)` — Writes sorted DataFrame to Excel with frozen header and auto-fit columns

**Scheduling:** `setup.sh` registers a cron job (`0 21 * * *`) that calls `run.sh`, which activates the venv and logs output.
