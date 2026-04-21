"""
Probe RecDesk to discover:
- All XHR/API endpoints called when the page loads
- Whether default state shows programs or requires filter interaction
- HTML structure of the program list once loaded
- Pagination mechanism
"""
import asyncio
import json
import re
from playwright.async_api import async_playwright

URL = "https://jcrec.recdesk.com/Community/Program"


async def main():
    api_calls: list[dict] = []
    json_payloads: list[tuple[str, object]] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        async def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                url = resp.url
                method = resp.request.method
                if any(k in url.lower() for k in ("program", "api", "search", "filter", "list")):
                    entry = {"method": method, "url": url, "status": resp.status, "ct": ct}
                    api_calls.append(entry)
                    if "json" in ct:
                        try:
                            body = await resp.json()
                            json_payloads.append((url, body))
                        except Exception:
                            pass
            except Exception:
                pass

        page.on("response", on_response)

        print("=== Navigating ===")
        await page.goto(URL, wait_until="networkidle", timeout=90_000)
        await page.wait_for_timeout(5_000)

        print("\n=== Page title ===")
        print(await page.title())

        print("\n=== Default body text snippet ===")
        body_text = await page.inner_text("body")
        print(body_text[:1500])

        print("\n=== All API/program-related calls observed ===")
        for c in api_calls:
            print(f"  [{c['status']}] {c['method']} {c['url']}")

        print("\n=== JSON payload summaries ===")
        for url, body in json_payloads:
            if isinstance(body, list):
                desc = f"LIST of {len(body)}"
                sample = body[0] if body else None
            elif isinstance(body, dict):
                desc = f"DICT keys={list(body.keys())[:10]}"
                sample = body
            else:
                desc = type(body).__name__
                sample = body
            print(f"  {url}\n    -> {desc}")
            if sample:
                print(f"    sample: {json.dumps(sample, default=str)[:500]}")

        # Try to detect program rows in DOM
        print("\n=== DOM probe: count various selectors ===")
        selectors = [
            "table tbody tr",
            ".program-item",
            ".programItem",
            "[class*='program-row']",
            ".Programs.list > div",
            ".Programs.list .program",
            "div.list div.row",
            ".program",
            ".ProgramList",
            ".programList",
            ".search-result",
            "[data-program-id]",
            ".panel",
            ".card",
        ]
        for sel in selectors:
            try:
                n = await page.locator(sel).count()
                if n:
                    print(f"  {sel}: {n}")
            except Exception:
                pass

        # Look for the loading container and what it becomes
        print("\n=== Programs container HTML ===")
        try:
            container = await page.query_selector(".Programs.list, .programs-list, #programs, .list")
            if container:
                html = await container.evaluate("el => el.outerHTML")
                print(html[:3000])
            else:
                print("Container not found")
        except Exception as e:
            print(f"err: {e}")

        # See all forms / inputs
        print("\n=== Visible form inputs ===")
        inputs = await page.query_selector_all("input, select")
        for i in inputs[:20]:
            try:
                name = await i.get_attribute("name") or ""
                ph = await i.get_attribute("placeholder") or ""
                val = await i.get_attribute("value") or ""
                tag = await i.evaluate("el => el.tagName")
                print(f"  {tag} name={name!r} placeholder={ph!r} value={val!r}")
            except Exception:
                pass

        # Try filling the age filter and see what happens
        print("\n=== Trying to fill age filter ===")
        for sel in [
            "input[name*='age' i]",
            "input[placeholder*='age' i]",
            "input[id*='age' i]",
        ]:
            loc = page.locator(sel)
            if await loc.count():
                try:
                    await loc.first.fill("8")
                    print(f"  Filled via {sel}")
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(3000)
                    break
                except Exception as e:
                    print(f"  err on {sel}: {e}")

        # Re-count rows after filter
        print("\n=== After age filter — selector counts ===")
        for sel in selectors:
            try:
                n = await page.locator(sel).count()
                if n:
                    print(f"  {sel}: {n}")
            except Exception:
                pass

        # If still nothing, try clicking a search/apply/filter button
        for sel in ["button:has-text('Search')", "button:has-text('Filter')", "button:has-text('Apply')", "input[type='submit']"]:
            loc = page.locator(sel)
            if await loc.count():
                try:
                    print(f"\n=== Clicking {sel} ===")
                    await loc.first.click()
                    await page.wait_for_timeout(4000)
                    break
                except Exception as e:
                    print(f"  err: {e}")

        # final dump
        print("\n=== FINAL — selector counts after interaction ===")
        for sel in selectors:
            try:
                n = await page.locator(sel).count()
                if n:
                    print(f"  {sel}: {n}")
            except Exception:
                pass

        # Save full HTML for inspection
        html = await page.content()
        with open("probe_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nSaved page HTML ({len(html)} bytes) to probe_page.html")

        # Save final API calls observed
        with open("probe_apis.json", "w") as f:
            json.dump(api_calls, f, indent=2)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
