"""Fetches FilterPrograms HTML pages via Playwright-acquired cookies."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from playwright.async_api import async_playwright

from .config import BASE_URL, FILTER_API, MAX_PAGES
from .parser import has_next_page

# Fallback to the pre-installed Chromium when the Playwright-managed binary is absent.
_FALLBACK_CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def _chromium_executable() -> str | None:
    path = Path(_FALLBACK_CHROMIUM)
    return str(path) if path.exists() else None

log = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _payload(page_num: int) -> dict:
    return {
        "ProgramName": "", "Code": "", "ProgramNameXS": "",
        "DateRangeSelection": "", "DateRangeFrom": "", "DateRangeTo": "",
        "ProgramType": "0", "Age": "", "Facility": "0", "Days": "0",
        "Pagination": {"CurrentPageIndex": page_num, "LoadMore": False},
    }


async def fetch_all_html_pages() -> list[str]:
    pages_html: list[str] = []
    async with async_playwright() as pw:
        launch_kwargs: dict = {
            "headless": True,
            "args": ["--no-sandbox", "--ignore-certificate-errors"],
        }
        fallback = _chromium_executable()
        if fallback:
            log.info("Using fallback Chromium: %s", fallback)
            launch_kwargs["executable_path"] = fallback
        browser = await pw.chromium.launch(**launch_kwargs)
        ctx = await browser.new_context(
            user_agent=_USER_AGENT,
            ignore_https_errors=True,
        )
        page = await ctx.new_page()
        log.info("Loading %s for cookies…", BASE_URL)
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(1_500)

        for page_num in range(1, MAX_PAGES + 1):
            resp = await ctx.request.post(
                FILTER_API,
                data=json.dumps(_payload(page_num)),
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
