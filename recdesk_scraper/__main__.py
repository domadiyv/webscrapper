"""Entry point: `python -m recdesk_scraper`."""
from __future__ import annotations

import asyncio
import logging
import sys
from collections import Counter

from .config import REGISTRATION_STATES, TARGET_AGE
from .exporter import save_excel
from .fetcher import fetch_all_html_pages
from .mailer import send_email
from .parser import parse_programs_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def _dedupe(programs: list[dict]) -> list[dict]:
    """Drop repeats of the same program.

    Keyed on the portal's programId: the portal legitimately lists distinct
    programs that share a name, dates and days (separate sections of the same
    class), so a (name, dates, days) key silently discards real programs.
    """
    seen, out = set(), []
    for p in programs:
        key = p.get("Program Id") or (p["Program Name"], p["Date(s)"], p["Day(s)"], p["Remaining"])
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _filter_new_registrations(programs: list[dict]) -> list[dict]:
    """Keep programs whose registration state is one we report on.

    Defaults to open-now plus opening-later. Matching on the status *text* alone
    does not work: the portal emits a badge only for non-default states, so a
    program that is open right now has no status text to match.
    """
    return [p for p in programs
            if p.get("Registration State", "unknown") in REGISTRATION_STATES]


async def run() -> None:
    log.info("=== RecDesk scraper started  target_age=%d ===", TARGET_AGE)
    html_pages = await fetch_all_html_pages()
    log.info("Fetched %d HTML pages", len(html_pages))

    programs: list[dict] = []
    for idx, html in enumerate(html_pages, 1):
        page_progs = parse_programs_html(html, TARGET_AGE)
        log.info("Page %d → %d matching programs", idx, len(page_progs))
        programs.extend(page_progs)

    before = len(programs)
    programs = _dedupe(programs)
    if len(programs) != before:
        log.info("Removed %d duplicate row(s)", before - len(programs))

    before = len(programs)
    by_state = Counter(p.get("Registration State", "unknown") for p in programs)
    programs = _filter_new_registrations(programs)
    log.info(
        "Registration states before filter: %s",
        ", ".join(f"{k}={v}" for k, v in sorted(by_state.items())) or "none",
    )
    log.info(
        "Kept %d of %d program(s) in states %s",
        len(programs), before, ",".join(sorted(REGISTRATION_STATES)),
    )

    log.info("Total matching programs: %d", len(programs))

    email_sent = False
    try:
        email_sent = send_email(programs)
    except Exception as exc:
        log.error("Email failed: %s", exc)

    if email_sent:
        log.info("Email sent successfully; skipping Excel export")
        print("\nEmail sent successfully. No Excel file saved.")
    else:
        out = save_excel(programs)
        print(f"\nDone. Output file: {out}")
        print(f"Programs found for age {TARGET_AGE}: {len(programs)}")


if __name__ == "__main__":
    asyncio.run(run())
