#!/usr/bin/env python3
"""
RecDesk Program Scraper
Scrapes https://jcrec.recdesk.com/Community/Program and extracts all programs
suitable for an 8-year-old, then saves results to a dated Excel file.
"""

import asyncio
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

URL = "https://jcrec.recdesk.com/Community/Program"
OUTPUT_DIR = Path(__file__).parent / "output"
TARGET_AGE = 8


# ---------------------------------------------------------------------------
# Age-range helpers
# ---------------------------------------------------------------------------

def age_includes(age_text: str, target: int = TARGET_AGE) -> bool:
    """Return True if *age_text* covers *target* age."""
    if not age_text:
        return False
    text = age_text.strip().lower()
    # strip common prefixes
    text = re.sub(r"^ages?\s*:?\s*", "", text)

    # "6-9", "6–9", "6 to 9"
    m = re.search(r"(\d+)\s*(?:[-–]|to)\s*(\d+)", text)
    if m:
        return int(m.group(1)) <= target <= int(m.group(2))

    # "8+", "8 & up", "8 and up", "8 or older"
    m = re.search(r"(\d+)\s*(?:\+|&\s*up|and\s*up|or\s*older)", text)
    if m:
        return int(m.group(1)) <= target

    # bare number
    m = re.fullmatch(r"\s*(\d+)\s*", text)
    if m:
        return int(m.group(1)) == target

    # fallback – grab all numbers and treat as range
    nums = [int(n) for n in re.findall(r"\d+", text)]
    if nums:
        return min(nums) <= target <= max(nums)

    return False


# ---------------------------------------------------------------------------
# DOM-scraping helpers
# ---------------------------------------------------------------------------

def _text(value) -> str:
    return (value or "").strip() or "N/A"


async def _safe_inner_text(el, selector: str) -> str:
    try:
        node = await el.query_selector(selector)
        if node:
            return (await node.inner_text()).strip()
    except Exception:
        pass
    return ""


async def extract_row_data(row) -> dict | None:
    """
    Pull fields from a single <tr> or program-card element.
    RecDesk community pages render a table with columns:
      Program Name | Age | Dates | Days | Opening | Remaining
    We try both table-cell indexing and named attribute selectors.
    """
    cells = await row.query_selector_all("td")

    if len(cells) >= 6:
        name     = _text(await cells[0].inner_text())
        age_raw  = _text(await cells[1].inner_text())
        dates    = _text(await cells[2].inner_text())
        days     = _text(await cells[3].inner_text())
        opening  = _text(await cells[4].inner_text())
        remaining = _text(await cells[5].inner_text())
    elif len(cells) >= 5:
        name     = _text(await cells[0].inner_text())
        age_raw  = _text(await cells[1].inner_text())
        dates    = _text(await cells[2].inner_text())
        days     = _text(await cells[3].inner_text())
        opening  = _text(await cells[4].inner_text())
        remaining = "N/A"
    else:
        # Try card-style layout with labelled spans/divs
        name      = await _safe_inner_text(row, ".program-name, .programName, h3, h4, .name")
        age_raw   = await _safe_inner_text(row, ".age, .ageRange, [data-label='Age']")
        dates     = await _safe_inner_text(row, ".dates, .date, [data-label='Dates'], [data-label='Date']")
        days      = await _safe_inner_text(row, ".days, .day, [data-label='Days']")
        opening   = await _safe_inner_text(row, ".opening, [data-label='Opening']")
        remaining = await _safe_inner_text(row, ".remaining, [data-label='Remaining']")
        if not name:
            return None

    if not age_includes(age_raw):
        return None

    return {
        "Program Name": name,
        "Age / Age Range": _text(age_raw),
        "Date(s)": dates,
        "Day(s)": days,
        "Opening": opening,
        "Remaining": remaining,
    }


# ---------------------------------------------------------------------------
# Network-intercept helper  (tries to grab JSON from XHR/fetch calls)
# ---------------------------------------------------------------------------

def _parse_api_programs(payload: list) -> list[dict]:
    """
    Try to normalise a list of dicts returned by the RecDesk API into our
    schema.  Field names vary by RecDesk version; we probe several candidates.
    """
    results = []
    for p in payload:
        if not isinstance(p, dict):
            continue

        name = (
            p.get("programName") or p.get("name") or p.get("ProgramName") or ""
        ).strip()

        age_raw = (
            p.get("ageRange") or p.get("age") or p.get("Age") or
            p.get("AgeRange") or p.get("minAge", "") or ""
        )
        if isinstance(age_raw, (int, float)):
            age_raw = str(int(age_raw))

        # Compose range string if separate min/max fields exist
        if not age_raw and ("minAge" in p or "maxAge" in p):
            lo = p.get("minAge", "")
            hi = p.get("maxAge", "")
            age_raw = f"{lo}-{hi}" if lo and hi else str(lo or hi)

        if not age_includes(str(age_raw)):
            continue

        dates = (
            p.get("dates") or p.get("startDate") or p.get("Dates") or
            p.get("sessionDates") or "N/A"
        )
        days = (
            p.get("days") or p.get("Days") or p.get("dayOfWeek") or "N/A"
        )
        opening   = str(p.get("openings",  p.get("opening",  p.get("Opening",  "N/A"))))
        remaining = str(p.get("remaining", p.get("Remaining", p.get("spotsLeft", "N/A"))))

        results.append({
            "Program Name": name or "N/A",
            "Age / Age Range": str(age_raw),
            "Date(s)": str(dates),
            "Day(s)": str(days),
            "Opening": opening,
            "Remaining": remaining,
        })
    return results


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

async def scrape() -> list[dict]:
    programs: list[dict] = []
    api_data: list[dict] = []          # filled if we catch an API response
    api_done = asyncio.Event()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        # ── intercept JSON API responses ──────────────────────────────────
        async def on_response(response):
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            url = response.url
            # RecDesk API paths contain "Program" or "program"
            if not re.search(r"program", url, re.I):
                return
            try:
                body = await response.json()
            except Exception:
                return

            # body may be a list directly or nested under a key
            rows = body if isinstance(body, list) else None
            if rows is None and isinstance(body, dict):
                for key in ("data", "programs", "results", "items", "Programs"):
                    if isinstance(body.get(key), list):
                        rows = body[key]
                        break

            if rows:
                log.info("Intercepted API response from %s (%d items)", url, len(rows))
                api_data.extend(rows)
                api_done.set()

        page.on("response", on_response)

        # ── navigate ──────────────────────────────────────────────────────
        log.info("Navigating to %s", URL)
        try:
            await page.goto(URL, wait_until="networkidle", timeout=90_000)
        except PlaywrightTimeout:
            log.warning("networkidle timed out; continuing anyway")

        # Give JS a moment to fire additional requests
        await page.wait_for_timeout(4_000)

        # ── use API data if captured ───────────────────────────────────────
        if api_data:
            log.info("Using API data (%d raw records)", len(api_data))
            programs = _parse_api_programs(api_data)
            log.info("After age filter: %d programs", len(programs))
            await browser.close()
            return programs

        # ── fall back to DOM scraping ─────────────────────────────────────
        log.info("No API data intercepted; falling back to DOM scraping")

        page_num = 1
        while True:
            log.info("Scraping DOM page %d", page_num)

            # Wait for at least one program row
            try:
                await page.wait_for_selector(
                    "table tbody tr, .program-item, .programItem, [class*='program-row']",
                    timeout=15_000,
                )
            except PlaywrightTimeout:
                log.warning("No program rows found on page %d", page_num)
                break

            # Scroll to bottom to trigger any lazy-loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1_500)

            rows = await page.query_selector_all(
                "table tbody tr, .program-item, .programItem, [class*='program-row']"
            )
            log.info("Found %d row elements", len(rows))

            for row in rows:
                try:
                    data = await extract_row_data(row)
                    if data:
                        programs.append(data)
                except Exception as exc:
                    log.debug("Row parse error: %s", exc)

            # ── pagination ────────────────────────────────────────────────
            next_btn = None
            for sel in [
                "a[aria-label='Next']:not(.disabled)",
                "button[aria-label='Next']:not([disabled])",
                ".pagination .next:not(.disabled) a",
                "li.next:not(.disabled) a",
                "a:text('Next')",
                "button:text('Next')",
            ]:
                try:
                    candidate = page.locator(sel).first
                    if await candidate.count() and await candidate.is_visible():
                        next_btn = candidate
                        break
                except Exception:
                    pass

            if next_btn is None:
                log.info("No next-page button found; done paginating")
                break

            log.info("Clicking next page button (page %d → %d)", page_num, page_num + 1)
            await next_btn.click()
            await page.wait_for_load_state("networkidle", timeout=30_000)
            await page.wait_for_timeout(2_000)
            page_num += 1

        await browser.close()

    log.info("Total programs for age %d: %d", TARGET_AGE, len(programs))
    return programs


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

def save_excel(programs: list[dict]) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)

    if not programs:
        log.warning("No programs found for age %d — saving empty file", TARGET_AGE)

    df = pd.DataFrame(programs, columns=[
        "Program Name", "Age / Age Range", "Date(s)", "Day(s)", "Opening", "Remaining"
    ])

    # Sort by date (best-effort: parse first token as date)
    def _sort_key(date_str: str):
        for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                first = date_str.split(" - ")[0].split("–")[0].strip()
                return datetime.strptime(first, fmt)
            except ValueError:
                pass
        return datetime.max

    df["_sort"] = df["Date(s)"].apply(_sort_key)
    df.sort_values("_sort", inplace=True)
    df.drop(columns=["_sort"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"programs_age8_{timestamp}.xlsx"

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Programs Age 8")

        ws = writer.sheets["Programs Age 8"]

        # Auto-fit column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

        # Freeze header row
        ws.freeze_panes = "A2"

    log.info("Saved → %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    log.info("=== RecDesk scraper started  target_age=%d ===", TARGET_AGE)
    programs = await scrape()
    path = save_excel(programs)
    print(f"\nDone. Output file: {path}")
    print(f"Programs found: {len(programs)}")


if __name__ == "__main__":
    asyncio.run(main())
