"""Entry point: `python -m recdesk_scraper`."""
from __future__ import annotations

import asyncio
import logging
import sys

from .config import TARGET_AGE
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
    seen, out = set(), []
    for p in programs:
        key = (p["Program Name"], p["Date(s)"], p["Day(s)"])
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


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

    log.info("Total matching programs: %d", len(programs))
    out = save_excel(programs)
    print(f"\nDone. Output file: {out}")
    print(f"Programs found for age {TARGET_AGE}: {len(programs)}")

    try:
        send_email(out, programs)
    except Exception as exc:
        log.error("Email failed: %s", exc)


if __name__ == "__main__":
    asyncio.run(run())
