"""Capture the live portal and audit it, in one command.

Run this on a machine with real network access to jcrec.recdesk.com:

    python scripts/capture_live.py

It fetches every page the portal serves, saves the raw HTML, then runs the
full per-program audit over it. Everything lands in `captures/`:

    captures/probe_filter_pageN.html   raw HTML, byte-for-byte as served
    captures/audit_report.txt          environment info + full audit output

`captures/` is committed on purpose. Push it and the exact live response can
be replayed and reviewed anywhere, by anyone, with no network:

    python scripts/verify_live.py --from captures

Exit code is that of the audit: 0 healthy, 1 if a check failed.
"""
from __future__ import annotations

import asyncio
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CAPTURES = ROOT / "captures"


def _environment_report() -> str:
    from recdesk_scraper import config
    try:
        from importlib.metadata import version
        pw_version = version("playwright")
    except Exception:
        pw_version = "not installed"

    lines = [
        "=" * 100,
        "CAPTURE ENVIRONMENT",
        "=" * 100,
        f"  captured at (UTC)   : {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"  captured at (local) : {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"  platform            : {platform.platform()}",
        f"  python              : {sys.version.split()[0]} ({sys.executable})",
        f"  playwright          : {pw_version}",
        "",
        f"  BASE_URL            : {config.BASE_URL}",
        f"  FILTER_API          : {config.FILTER_API}",
        f"  TARGET_AGE          : {config.TARGET_AGE}",
        f"  MAX_PAGES           : {config.MAX_PAGES}",
        f"  REGISTRATION_STATES : {','.join(sorted(config.REGISTRATION_STATES))}",
    ]
    return "\n".join(lines)


def _fetch() -> list[str]:
    from recdesk_scraper.fetcher import fetch_all_html_pages
    return asyncio.run(fetch_all_html_pages())


def main() -> int:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    env_report = _environment_report()
    print(env_report + "\n")

    print("Fetching the live portal…")
    try:
        pages = _fetch()
    except Exception as exc:
        msg = str(exc)
        print(f"\nFETCH FAILED: {type(exc).__name__}\n{msg[:1500]}\n")
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            print("Playwright's browser is missing. Install it with:\n"
                  "    python -m playwright install chromium")
        elif "ERR_TUNNEL_CONNECTION_FAILED" in msg or "ERR_PROXY" in msg:
            print("The network refused the connection — this machine cannot reach\n"
                  "jcrec.recdesk.com (proxy, VPN or firewall in the way).")
        elif "ERR_NAME_NOT_RESOLVED" in msg:
            print("DNS could not resolve jcrec.recdesk.com — check your connection.")
        return 2

    if not pages:
        print("\nFETCH RETURNED NO PAGES — the portal answered, but with nothing to parse.")
        return 2

    CAPTURES.mkdir(parents=True, exist_ok=True)
    for stale in CAPTURES.glob("probe_filter_page*.html"):
        stale.unlink()
    for i, html in enumerate(pages, 1):
        dest = CAPTURES / f"probe_filter_page{i}.html"
        dest.write_text(html, encoding="utf-8")
        print(f"  saved {dest.relative_to(ROOT)}  ({len(html):,} bytes)")

    print(f"\nRunning the audit over {len(pages)} captured page(s)…\n")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_live.py"), "--from", str(CAPTURES)],
        capture_output=True, text=True,
    )
    audit_output = proc.stdout + (("\n[stderr]\n" + proc.stderr) if proc.stderr.strip() else "")
    print(audit_output)

    report = CAPTURES / "audit_report.txt"
    report.write_text(
        env_report
        + f"\n\n  pages fetched       : {len(pages)}\n"
        + f"  audit exit code     : {proc.returncode}\n\n"
        + audit_output,
        encoding="utf-8",
    )

    print("=" * 100)
    print(f"Raw HTML + report written to {CAPTURES.relative_to(ROOT)}/")
    print("Share the result by committing it:")
    print("    git add captures && git commit -m 'chore: live portal capture' && git push")
    print("=" * 100)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
