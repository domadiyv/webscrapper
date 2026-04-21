# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Layout

```
recdesk_scraper/       package — one module per responsibility
  config.py            env + .env loading, paths, EmailConfig
  age.py               age_includes, extract_age_from_name
  parser.py            parse_programs_html, has_next_page, COLUMNS
  fetcher.py           Playwright cookie load + FilterPrograms POST loop
  exporter.py          save_excel (sort, autofit, freeze header)
  mailer.py            send_email — HTML list body + Excel attachment
  __main__.py          `python -m recdesk_scraper`
tests/
  fixtures/            probe_filter_pageN.html (live-portal captures)
  conftest.py          puts project root on sys.path
  test_age_includes.py, test_extract_age_from_name.py, test_parse_programs_html.py
scripts/               probe scripts for investigating portal changes
output/                generated XLSX (gitignored)
logs/                  run.sh output (gitignored)
.env / .env.example    SMTP credentials (.env gitignored)
```

## Setup

```bash
# Unix (one-time)
bash setup.sh

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium

# Configure email (optional)
cp .env.example .env     # then fill in SMTP_* and EMAIL_TO
```

## Running

```bash
python -m recdesk_scraper          # run the scraper
pytest tests/ -v                   # run tests
```

Windows:
```
.venv\Scripts\python.exe -m recdesk_scraper
.venv\Scripts\python.exe -m pytest tests/ -v
```

Output: `output/programs_age<AGE>_YYYYMMDD_HHMMSS.xlsx`.

## Data flow

1. Playwright loads `/Community/Program` once to obtain session cookies.
2. For each page N, POST `/Community/Program/FilterPrograms` with `Pagination.CurrentPageIndex = N`. The endpoint returns **HTML** (not JSON).
3. `parse_programs_html` walks the tbody, tracking `category-header` rows to tag each following `sub-category-header` + `hidden-xs` detail pair.
4. Each program's Ages cell (`"7y - 14y"`) is tested with `age_includes`. When the cell is empty/dashed, fall back to `extract_age_from_name` which extracts `"Ages 7-11"`-style phrases from the title.
5. **FULL programs are skipped** — if the Remaining cell contains the `FULL` badge, the program is excluded.
6. Each program's registration URL (`…/Community/Program/Detail?programId=…`) is captured as an absolute link.
7. Stop paginating when `has_next_page` reports no higher numeric anchor. Dedupe by (name, dates, days). Write sorted Excel as a local archive. Send email if SMTP configured.

## Email

`mailer.send_email(programs)` builds a multipart message rendered **directly in the body** — no attachment required:
- **Text** part: numbered list of programs with URL on its own line.
- **HTML** part: styled table where each Program Name is a clickable link to the RecDesk registration page.

Config is loaded from `.env` (via `python-dotenv`) or environment. Required: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO`. Optional: `SMTP_PORT` (default 587), `SMTP_TLS` (default true), `EMAIL_FROM` (defaults to `SMTP_USER`). If any required var is missing, email is skipped and the run still succeeds.

Gmail requires an **App Password** (not the account password): https://support.google.com/accounts/answer/185833

## Secrets & public-repo hygiene

- `.gitignore` excludes `.env`, `.venv/`, `__pycache__/`, `output/`, `logs/`, editor caches.
- `.env` is never committed. `.env.example` is the template.
- No secrets live in source — all sensitive values come from env vars loaded at runtime.

## Scheduling

`setup.sh` registers `0 21 * * * run.sh` on Linux/macOS. `run.sh` activates the venv and invokes `python -m recdesk_scraper`, logging to `logs/scraper_YYYYMMDD_HHMMSS.log`. Windows users should wire this up via Task Scheduler manually.

## Regenerating test fixtures

If the portal markup changes, re-run `scripts/probe3.py` (hits FilterPrograms for 3 pages) and move the captured HTML into `tests/fixtures/`.
