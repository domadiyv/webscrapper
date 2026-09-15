# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Layout

```
recdesk_scraper/       package — one module per responsibility
  config.py            env + .env loading, paths, EmailConfig
  age.py               age_includes, grade_bounds/grade_age_range/grade_includes,
                       has_age_info, extract_age_from_name
  parser.py            parse_programs_html, age_eligible, has_next_page, COLUMNS
  fetcher.py           Playwright cookie load + FilterPrograms POST loop
  exporter.py          save_excel (sort, autofit, freeze header)
  mailer.py            send_email — HTML list body + Excel attachment
  __main__.py          `python -m recdesk_scraper`
tests/
  fixtures/            probe_filter_pageN.html (live-portal captures)
  conftest.py          puts project root on sys.path
  test_age_includes.py, test_extract_age_from_name.py, test_parse_programs_html.py,
  test_registration_pipeline.py, test_grade_and_age_eligibility.py
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
4. Age eligibility is decided by **`parser.age_eligible(program, target_age)`**, which
   returns `(eligible, reason)`. Production and `scripts/verify_live.py` both call it,
   so the audit cannot drift from the filtering that actually runs. Precedence:
   1. **Ages cell** (`"7y - 14y"`) via `age_includes` — falling back to
      `extract_age_from_name`, which pulls `"Ages 7-11"`-style phrases from the title.
   2. **Grades cell** (`"2 - 4"`) via `grade_age_range`, since the portal restricts a
      program by age *or* by grade and a grade-based program leaves Ages unset. A child
      in grade N is taken to be **age N+5 to N+6**, so grades 2-4 → ages 7-10.
      Kindergarten is grade 0, pre-K is -1.
   3. **Neither** → no restriction, eligible at every age, which is how the portal
      itself treats these.

   Two portal conventions make this subtle, and both are load-bearing:
   - The "no restriction" placeholder is **`- Not specified`**, *not* `-` or an empty
     cell. Testing for emptiness silently drops every grade-based program — use
     `has_age_info` / `grade_bounds`, which look for a usable value.
   - A **lone age is a minimum**, not an exact match: `"18y"` is a program titled
     "18+", and the portal returns it when filtering ages 18 through 50. When it
     means exactly one age it writes a range instead — `"8y - 8y"`.
5. **FULL programs are skipped** — if the Remaining cell contains the `FULL` badge, the program is excluded.
6. Each program's registration URL (`…/Community/Program/Detail?programId=…`) is captured as an absolute link.
7. Each program's **registration state** is classified. The portal renders a status-badge row (which sits *above* the detail row) **only for non-default states** — `Registration ended on <date>`, `Registration begins on <date>`, `No online registration`. A program that is simply open right now has **no badge at all**; its only signal is the `Register Now` button in the detail row's trailing cell. States: `open`, `upcoming`, `waitlist`, `ended`, `offline`, `unknown`. Never filter on the status *text* alone — open programs have none.
8. Programs are filtered to the states listed in `REGISTRATION_STATES` (default `open,upcoming`).
9. If no programs match, a "no new programs" email is sent instead of an empty list.
10. Stop paginating when `has_next_page` reports the pager's `next` control disabled (falling back to the max numeric anchor). Dedupe by **programId** — the portal lists distinct programs that share a name, dates and days, so a (name, dates, days) key silently drops real programs. Write sorted Excel as a local archive. Send email if SMTP configured.

## Email

`mailer.send_email(programs)` builds a multipart message rendered **directly in the body** — no attachment required:
- **Text** part: numbered list of programs with URL on its own line.
- **HTML** part: styled table where each Program Name is a clickable link to the RecDesk registration page.

Config is loaded from `.env` (via `python-dotenv`) or environment. Required: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO`. Optional: `SMTP_PORT` (default 587), `SMTP_TLS` (default true), `EMAIL_FROM` (defaults to `SMTP_USER`). If any required var is missing, email is skipped and the run still succeeds.

Scraper tuning env vars: `TARGET_AGE` (default 8), `MAX_PAGES` (default 50), `REGISTRATION_STATES` (default `open,upcoming`; set to `upcoming` alone to be notified only about registrations that have not started yet).

Gmail requires an **App Password** (not the account password): https://support.google.com/accounts/answer/185833

## Secrets & public-repo hygiene

- `.gitignore` excludes `.env`, `.venv/`, `__pycache__/`, `output/`, `logs/`, editor caches.
- `.env` is never committed. `.env.example` is the template.
- No secrets live in source — all sensitive values come from env vars loaded at runtime.

## Scheduling

`setup.sh` registers `0 21 * * * run.sh` on Linux/macOS. `run.sh` activates the venv and invokes `python -m recdesk_scraper`, logging to `logs/scraper_YYYYMMDD_HHMMSS.log`. Windows users should wire this up via Task Scheduler manually.

## Verifying against the live portal

`scripts/verify_live.py` audits the scraper program by program against the real
site. It prints every program the portal lists with its extracted fields, its
registration state, and the exact reason it was kept or dropped — then runs a set
of checks and exits non-zero if anything looks wrong (nothing classified `open`,
programs it could not classify, or age-eligible programs that all vanish at the
registration filter — the signature of the bug that silenced the report).

### One-command live capture

`scripts/capture_live.py` fetches the live portal, saves the raw HTML to
`captures/`, runs the audit over it and writes `captures/audit_report.txt`.
`captures/` is tracked on purpose — commit it and the exact live response can be
replayed anywhere with `verify_live.py --from captures`, no network needed.

```bash
bash run_live_test.sh          # macOS/Linux — bootstraps the venv, then captures
.\run_live_test.ps1            # Windows PowerShell — same
python scripts/capture_live.py # if the venv is already set up
```

Exit codes: 0 healthy, 1 an audit check failed, 2 the fetch itself failed
(the script names the cause — missing browser, DNS, proxy/firewall).

### Manual audit

```bash
python scripts/verify_live.py                       # hit the live portal
python scripts/verify_live.py --save captures/      # ...and keep the raw HTML
python scripts/verify_live.py --from tests/fixtures # offline re-run
python scripts/verify_live.py --age 10              # audit a different age
```

Because it uses `parser.extract_programs` — the same extraction production runs —
the audit cannot drift from the real scraper.

## Regenerating test fixtures

If the portal markup changes, re-run `scripts/probe3.py` (hits FilterPrograms for 3 pages) and move the captured HTML into `tests/fixtures/`.
