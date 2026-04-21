"""
Probe2 — capture the FilterPrograms POST response body and look for pagination.
Also try clicking Search button explicitly to load all programs (not just age=8).
"""
import asyncio
import json
from playwright.async_api import async_playwright

URL = "https://jcrec.recdesk.com/Community/Program"


async def main():
    captured = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        async def on_response(resp):
            if "FilterPrograms" in resp.url:
                try:
                    body = await resp.text()
                    captured.append({
                        "url": resp.url,
                        "method": resp.request.method,
                        "post_data": resp.request.post_data,
                        "ct": resp.headers.get("content-type", ""),
                        "body_len": len(body),
                        "body_preview": body[:3000],
                    })
                    print(f"[CAPTURED] {resp.request.method} {resp.url} ct={resp.headers.get('content-type')} body_len={len(body)}")
                except Exception as e:
                    print(f"err reading body: {e}")

        page.on("response", on_response)

        print("=== Navigate (initial) ===")
        await page.goto(URL, wait_until="networkidle", timeout=90_000)
        await page.wait_for_timeout(3000)

        print("\n=== Click Search WITHOUT any filter (load all) ===")
        for sel in ["button:has-text('Search')", "input[type='submit']", "a:has-text('Search')"]:
            loc = page.locator(sel)
            cnt = await loc.count()
            if cnt:
                print(f"Found {cnt} of {sel}")
                try:
                    await loc.first.click()
                    print(f"Clicked {sel}")
                    await page.wait_for_timeout(5000)
                    break
                except Exception as e:
                    print(f"err clicking {sel}: {e}")

        print(f"\n=== Total captures: {len(captured)} ===")
        for c in captured[-3:]:
            print(f"\n[{c['method']}] {c['url']}")
            print(f"  ct={c['ct']}  body_len={c['body_len']}")
            print(f"  POST data: {c['post_data'][:500] if c['post_data'] else 'N/A'}")
            print(f"  Body preview:\n{c['body_preview'][:2000]}")

        # count programs after search-all
        n = await page.locator("[data-program-id]").count()
        print(f"\n=== After Search (no filter): [data-program-id] count = {n} ===")

        # Look for pagination
        print("\n=== Pagination probe ===")
        for sel in [
            ".pagination", "ul.pagination", ".pager", "[class*='pag']",
            "a:has-text('Next')", "a:has-text('»')", ".page-link",
        ]:
            cnt = await page.locator(sel).count()
            if cnt:
                print(f"  {sel}: {cnt}")
                try:
                    text = await page.locator(sel).first.inner_text()
                    print(f"    text: {text!r}")
                except Exception:
                    pass

        # save full final HTML
        html = await page.content()
        with open("probe_page2.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nSaved full final page ({len(html)} bytes) → probe_page2.html")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
