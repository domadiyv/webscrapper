"""
Probe3 — call FilterPrograms POST directly via Playwright's request API.
Get all 3 pages. Save raw HTML for each.
"""
import asyncio
import json
from playwright.async_api import async_playwright

URL = "https://jcrec.recdesk.com/Community/Program"
API = "https://jcrec.recdesk.com/Community/Program/FilterPrograms"


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # Visit once to obtain anti-forgery cookies/tokens
        await page.goto(URL, wait_until="networkidle", timeout=90_000)
        await page.wait_for_timeout(2000)

        for pg in range(1, 5):
            payload = {
                "ProgramName": "",
                "Code": "",
                "ProgramNameXS": "",
                "DateRangeSelection": "",
                "DateRangeFrom": "",
                "DateRangeTo": "",
                "ProgramType": "0",
                "Age": "",
                "Facility": "0",
                "Days": "0",
                "Pagination": {"CurrentPageIndex": pg, "LoadMore": False},
            }
            resp = await ctx.request.post(API, data=json.dumps(payload), headers={
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/html, */*; q=0.01",
            })
            body = await resp.text()
            print(f"\n=== Page {pg}: status={resp.status} body_len={len(body)} ===")
            with open(f"probe_filter_page{pg}.html", "w", encoding="utf-8") as f:
                f.write(body)

            # Quick stats: count category-header, sub-category-header, data-program-id
            import re
            cats = re.findall(r'category-header[^>]*>\s*<span[^>]*>Category:</span>\s*<strong>([^<]+)</strong>', body)
            subs = re.findall(r'class="sub-category-header[^"]*"', body)
            pids = re.findall(r'data-program-id="(\d+)"', body)
            print(f"  Categories: {cats}")
            print(f"  Sub-category rows: {len(subs)}")
            print(f"  Unique program-ids: {len(set(pids))} (raw {len(pids)})")
            # Has next page? Look for pagination
            pag = re.search(r'pagination[^>]*>(.*?)</ul>', body, re.DOTALL)
            if pag:
                pag_text = re.sub(r'<[^>]+>', ' ', pag.group(0))
                pag_text = re.sub(r'\s+', ' ', pag_text).strip()
                print(f"  Pagination: {pag_text[:200]}")
            else:
                print(f"  No pagination block found in body")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
