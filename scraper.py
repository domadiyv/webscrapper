#!/usr/bin/env python3
"""
RecDesk Program Scraper.

Calls the RecDesk FilterPrograms endpoint with pagination, parses the returned
HTML, filters programs that include TARGET_AGE, and writes results to Excel.
"""

import asyncio
import json
import logging
import os
import re
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

BASE_URL = "https://jcrec.recdesk.com/Community/Program"
FILTER_API = "https://jcrec.recdesk.com/Community/Program/FilterPrograms"
OUTPUT_DIR = Path(__file__).parent / "output"
TARGET_AGE = 8
MAX_PAGES = 50  # safety cap


# ---------------------------------------------------------------------------
# Age-range parsing
# ---------------------------------------------------------------------------

def age_includes(age_text: str, target: int = TARGET_AGE) -> bool:
    """Return True if `age_text` covers `target` age.

    Handles forms seen on the live portal:
      "7y - 14y", "8y - 8y", "Ages 7-11", "Ages 8 to 18",
      "Ages 12+", "8 and up", "8 & up", "8 or older",
      single number "8", "Ages: 7-9".
    """
    if not age_text:
        return False
    text = age_text.strip().lower()
    text = re.sub(r"^ages?\s*:?\s*", "", text)
    text = text.replace("y", " ")  # "7y - 14y" -> "7  - 14 "

    m = re.search(r"(\d+)\s*(?:[-–—]|to)\s*(\d+)", text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return lo <= target <= hi

    m = re.search(r"(\d+)\s*(?:\+|&\s*up|and\s*up|or\s*older|or\s*up)", text)
    if m:
        return int(m.group(1)) <= target

    m = re.fullmatch(r"\s*(\d+)\s*", text)
    if m:
        return int(m.group(1)) == target

    nums = [int(n) for n in re.findall(r"\d+", text)]
    if len(nums) == 1:
        return nums[0] == target
    if len(nums) >= 2:
        return min(nums) <= target <= max(nums)
    return False


def extract_age_from_name(name: str) -> str:
    """Pull an age phrase out of a program name (fallback when Ages cell empty).

    Example: "2026 Spring - Boxing @ MS# 7 Ages 7-11 (Mon/Wed)" -> "Ages 7-11"
    """
    if not name:
        return ""
    m = re.search(
        r"ages?\s*[:\-]?\s*\d+\s*(?:[-–—to]+\s*\d+|\+|&\s*up|and\s*up|or\s*older)?",
        name,
        re.IGNORECASE,
    )
    return m.group(0).strip() if m else ""


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

# Single-source-of-truth schema. Used everywhere we shape program rows.
COLUMNS = ["Program Name", "Category", "Age / Age Range",
           "Date(s)", "Day(s)", "Opening", "Remaining"]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _cell_value_after_label(tr, label: str) -> str:
    """Inside a <tr>, find a <td> whose first child text is `label` and return
    the text under it (the value lives in the small.text-muted span/<small>)."""
    for td in tr.find_all("td", recursive=False):
        head = td.find(class_="text-semibold")
        if head and _clean(head.get_text()).lower() == label.lower():
            small = td.find("small")
            if small:
                return _clean(small.get_text(" ", strip=True))
            return _clean(td.get_text(" ", strip=True).removeprefix(label).strip())
    return ""


def parse_programs_html(html: str, target_age: int = TARGET_AGE) -> list[dict]:
    """Parse a FilterPrograms HTML response and return matching programs."""
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.select_one("table.table-vcenter > tbody")
    if not tbody:
        return []

    results: list[dict] = []
    current_category = "N/A"

    children = [c for c in tbody.find_all("tr", recursive=False)]
    i = 0
    while i < len(children):
        tr = children[i]

        # Category header row
        cat_td = tr.find("td", class_="category-header")
        if cat_td:
            strong = cat_td.find("strong")
            if strong:
                current_category = _clean(strong.get_text())
            i += 1
            continue

        cls = " ".join(tr.get("class", []))
        if "sub-category-header" in cls:
            # Program title row
            link = tr.find("a", href=re.compile(r"programId="))
            name = _clean(link.get_text()) if link else "N/A"

            # The next non-mobile detail row is the desktop "hidden-xs" row.
            detail_tr = None
            j = i + 1
            while j < len(children):
                next_tr = children[j]
                ncls = " ".join(next_tr.get("class", []))
                if "sub-category-header" in ncls or next_tr.find("td", class_="category-header"):
                    break
                if "hidden-xs" in ncls:
                    detail_tr = next_tr
                    break
                j += 1

            ages = dates = days = opening = remaining = ""
            if detail_tr is not None:
                dates    = _cell_value_after_label(detail_tr, "Dates")
                days     = _cell_value_after_label(detail_tr, "Days")
                ages     = _cell_value_after_label(detail_tr, "Ages")
                opening  = _cell_value_after_label(detail_tr, "Openings")
                remaining = _cell_value_after_label(detail_tr, "Remaining")

            # If Ages cell is empty/dash, fall back to parsing the program name
            if not ages or ages.strip() in {"-", "N/A"}:
                ages = extract_age_from_name(name) or ages

            if age_includes(ages, target_age):
                results.append({
                    "Program Name": name,
                    "Category": current_category,
                    "Age / Age Range": ages or "N/A",
                    "Date(s)": dates or "N/A",
                    "Day(s)": days or "N/A",
                    "Opening": opening or "N/A",
                    "Remaining": remaining or "N/A",
                })
        i += 1

    return results


def has_next_page(html: str, current_page: int) -> bool:
    """Return True if the pagination block links to a page > current_page."""
    soup = BeautifulSoup(html, "html.parser")
    pagination = soup.select_one("ul.pagination, .pagination")
    if not pagination:
        return False
    # Look for any anchor whose text is a number > current_page, or a "»" Next link.
    for a in pagination.find_all("a"):
        txt = _clean(a.get_text())
        if txt.isdigit() and int(txt) > current_page:
            return True
        if txt in ("»", "Next") and "disabled" not in " ".join(a.parent.get("class", [])):
            # Conservative: only treat » as next if some numeric > current exists too
            pass
    # Also detect by max numeric link
    nums = [int(_clean(a.get_text())) for a in pagination.find_all("a")
            if _clean(a.get_text()).isdigit()]
    return bool(nums) and max(nums) > current_page


# ---------------------------------------------------------------------------
# Network — Playwright drives only the initial page-load to get cookies, then
# we hit the JSON-POST FilterPrograms endpoint directly per page.
# ---------------------------------------------------------------------------

async def fetch_all_html_pages() -> list[str]:
    pages_html: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
        )
        page = await ctx.new_page()
        log.info("Loading %s for cookies…", BASE_URL)
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(1_500)

        for page_num in range(1, MAX_PAGES + 1):
            payload = {
                "ProgramName": "", "Code": "", "ProgramNameXS": "",
                "DateRangeSelection": "", "DateRangeFrom": "", "DateRangeTo": "",
                "ProgramType": "0", "Age": "", "Facility": "0", "Days": "0",
                "Pagination": {"CurrentPageIndex": page_num, "LoadMore": False},
            }
            resp = await ctx.request.post(
                FILTER_API,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "text/html, */*; q=0.01",
                    "Referer": BASE_URL,
                },
            )
            if resp.status != 200:
                log.warning("Page %d returned status %d", page_num, resp.status)
                break
            body = await resp.text()
            log.info("Page %d fetched (%d bytes)", page_num, len(body))
            pages_html.append(body)
            if not has_next_page(body, page_num):
                log.info("No further pages after %d", page_num)
                break

        await browser.close()
    return pages_html


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

def _date_sort_key(date_str: str):
    if not date_str or date_str == "N/A":
        return datetime.max
    first = re.split(r"\s*[-–]\s*", date_str)[0].strip()
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%m/%d/%y"):
        try:
            return datetime.strptime(first, fmt)
        except ValueError:
            continue
    return datetime.max


def save_excel(programs: list[dict]) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    df = pd.DataFrame(programs, columns=COLUMNS)
    if not df.empty:
        df["_sort"] = df["Date(s)"].apply(_date_sort_key)
        df.sort_values(["_sort", "Program Name"], inplace=True)
        df.drop(columns=["_sort"], inplace=True)
        df.reset_index(drop=True, inplace=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"programs_age{TARGET_AGE}_{timestamp}.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=f"Programs Age {TARGET_AGE}")
        ws = writer.sheets[f"Programs Age {TARGET_AGE}"]
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)
        ws.freeze_panes = "A2"
    log.info("Saved → %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Email (optional — requires env vars; silently skipped otherwise)
# ---------------------------------------------------------------------------

def maybe_send_email(out_path: Path, programs: list[dict]) -> None:
    """Send the Excel file as an email attachment if SMTP env vars are set.

    Required env vars:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_TO
    Optional: EMAIL_FROM (defaults to SMTP_USER), SMTP_TLS (default 'true')
    """
    host = os.environ.get("SMTP_HOST")
    to_addr = os.environ.get("EMAIL_TO")
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASSWORD")
    if not all([host, to_addr, user, pw]):
        log.info("Email not sent (SMTP env vars not configured)")
        return
    port = int(os.environ.get("SMTP_PORT", "587"))
    from_addr = os.environ.get("EMAIL_FROM", user)
    use_tls = os.environ.get("SMTP_TLS", "true").lower() == "true"

    msg = EmailMessage()
    msg["Subject"] = f"RecDesk Programs (age {TARGET_AGE}) — {datetime.now():%Y-%m-%d}"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(
        f"Daily RecDesk scrape complete.\n\n"
        f"Programs matching age {TARGET_AGE}: {len(programs)}\n"
        f"Attached: {out_path.name}\n"
    )
    with open(out_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=out_path.name,
        )
    with smtplib.SMTP(host, port) as smtp:
        if use_tls:
            smtp.starttls()
        smtp.login(user, pw)
        smtp.send_message(msg)
    log.info("Emailed report to %s", to_addr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    log.info("=== RecDesk scraper started  target_age=%d ===", TARGET_AGE)
    html_pages = await fetch_all_html_pages()
    log.info("Fetched %d HTML pages", len(html_pages))

    programs: list[dict] = []
    for idx, html in enumerate(html_pages, 1):
        page_progs = parse_programs_html(html, TARGET_AGE)
        log.info("Page %d → %d matching programs", idx, len(page_progs))
        programs.extend(page_progs)

    # Dedupe — portal occasionally lists same program twice with different ids
    seen, deduped = set(), []
    for p in programs:
        key = (p["Program Name"], p["Date(s)"], p["Day(s)"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    if len(deduped) != len(programs):
        log.info("Removed %d duplicate row(s)", len(programs) - len(deduped))
    programs = deduped

    log.info("Total matching programs: %d", len(programs))
    out = save_excel(programs)
    print(f"\nDone. Output file: {out}")
    print(f"Programs found for age {TARGET_AGE}: {len(programs)}")

    try:
        maybe_send_email(out, programs)
    except Exception as exc:
        log.error("Email failed: %s", exc)


if __name__ == "__main__":
    asyncio.run(main())
