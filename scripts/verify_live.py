"""Audit the scraper against the live portal, program by program.

Run this on a machine with real network access to jcrec.recdesk.com:

    python scripts/verify_live.py                  # hit the live portal
    python scripts/verify_live.py --save captures/ # ...and keep the raw HTML
    python scripts/verify_live.py --from tests/fixtures   # offline re-run

For every program the portal lists it prints the extracted fields, the
registration state, and the exact reason it was KEPT or DROPPED — so you can
open the portal side by side and confirm each verdict yourself.

Exit code is 1 if the audit finds something suspicious (see CHECKS at the end).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recdesk_scraper.age import age_includes
from recdesk_scraper.config import REGISTRATION_STATES, TARGET_AGE
from recdesk_scraper.parser import (
    STATE_OPEN,
    STATE_UPCOMING,
    _is_full,
    extract_programs,
    has_next_page,
)
from recdesk_scraper.__main__ import _dedupe, _filter_new_registrations

BAR = "=" * 100


def _verdict(p: dict, target_age: int) -> tuple[bool, str]:
    """Return (kept, reason) for one program, mirroring the production pipeline."""
    if not age_includes(p["Age / Age Range"], target_age):
        return False, f"age {target_age} not in {p['Age / Age Range']!r}"
    if _is_full(p["Remaining"]):
        return False, "FULL"
    if p["Registration State"] not in REGISTRATION_STATES:
        return False, f"registration state {p['Registration State']!r} ({p['Registration Status']})"
    return True, f"state={p['Registration State']}"


async def _load_live(save_dir: Path | None) -> list[str]:
    from recdesk_scraper.fetcher import fetch_all_html_pages
    pages = await fetch_all_html_pages()
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)
        for i, html in enumerate(pages, 1):
            (save_dir / f"probe_filter_page{i}.html").write_text(html, encoding="utf-8")
        print(f"Saved {len(pages)} raw page(s) to {save_dir}/\n")
    return pages


def _load_dir(d: Path) -> list[str]:
    files = sorted(d.glob("probe_filter_page*.html"),
                   key=lambda f: int("".join(c for c in f.stem if c.isdigit()) or 0))
    if not files:
        sys.exit(f"no probe_filter_page*.html found in {d}")
    print(f"Reading {len(files)} saved page(s) from {d}/\n")
    return [f.read_text(encoding="utf-8") for f in files]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", type=Path, help="read saved HTML instead of fetching")
    ap.add_argument("--save", type=Path, help="write the fetched HTML here")
    ap.add_argument("--age", type=int, default=TARGET_AGE)
    args = ap.parse_args()

    pages = _load_dir(args.src) if args.src else asyncio.run(_load_live(args.save))

    print(BAR)
    print(f"LIVE AUDIT — target age {args.age} | reporting states: {','.join(sorted(REGISTRATION_STATES))}")
    print(BAR)

    every: list[dict] = []
    for n, html in enumerate(pages, 1):
        progs = extract_programs(html)
        every.extend(progs)
        print(f"\n--- PAGE {n}: {len(progs)} programs | has_next_page -> {has_next_page(html, n)}")
        for p in progs:
            kept, why = _verdict(p, args.age)
            print(f"  [{'KEEP' if kept else 'drop'}] id={p['Program Id']:>6}  {p['Program Name'][:56]:56}")
            print(f"         cat={p['Category'][:20]:20} ages={p['Age / Age Range']:12} "
                  f"rem={p['Remaining']:>6}  state={p['Registration State']:9} "
                  f"status={p['Registration Status'][:34]}")
            print(f"         -> {'kept: ' if kept else 'dropped: '}{why}")

    print("\n" + BAR)
    print(f"TOTALS — {len(every)} programs across {len(pages)} page(s)")
    print(BAR)
    print("  registration states :", dict(Counter(p["Registration State"] for p in every)))
    age_ok = [p for p in every if age_includes(p["Age / Age Range"], args.age)]
    not_full = [p for p in age_ok if not _is_full(p["Remaining"])]
    print(f"  age {args.age} matches      : {len(age_ok)}")
    print(f"  ...and not FULL     : {len(not_full)}")

    deduped = _dedupe(not_full)
    final = _filter_new_registrations(deduped)
    print(f"  ...after dedupe     : {len(deduped)}")
    print(f"  ...after reg filter : {len(final)}   <- this is what gets emailed")

    print("\n" + BAR)
    print(f"EMAIL WOULD CONTAIN {len(final)} PROGRAM(S)")
    print(BAR)
    for i, p in enumerate(sorted(final, key=lambda x: x["Program Name"]), 1):
        print(f"{i:3d}. {p['Program Name']}")
        print(f"     {p['Category']} | ages {p['Age / Age Range']} | {p['Date(s)']} | {p['Day(s)']}")
        print(f"     {p['Registration Status']} | remaining {p['Remaining']}")
        print(f"     {p['URL']}")

    # ---- CHECKS: things that would indicate the scraper is still broken -----
    print("\n" + BAR)
    print("CHECKS")
    print(BAR)
    problems = []

    open_now = [p for p in every if p["Registration State"] == STATE_OPEN]
    if not open_now:
        problems.append(
            "No program was classified 'open'. The portal almost always has some "
            "'Register Now' programs — the badge/button markup may have changed.")
    else:
        print(f"  OK   {len(open_now)} program(s) classified 'open' (Register Now button present)")

    unknown = [p for p in every if p["Registration State"] == "unknown"]
    if unknown:
        problems.append(
            f"{len(unknown)} program(s) could not be classified; markup may have changed: "
            + ", ".join(p["Program Name"][:40] for p in unknown[:5]))
    else:
        print("  OK   every program got a registration state")

    no_id = [p for p in every if not p["Program Id"]]
    if no_id:
        problems.append(f"{len(no_id)} program(s) have no programId — dedupe will be unreliable")
    else:
        print("  OK   every program has a programId")

    ids = [p["Program Id"] for p in every]
    if len(ids) != len(set(ids)):
        dupes = [k for k, v in Counter(ids).items() if v > 1]
        print(f"  note {len(dupes)} programId(s) appear on more than one page (dedupe handles this)")

    upcoming = [p for p in every if p["Registration State"] == STATE_UPCOMING]
    print(f"  note {len(upcoming)} program(s) have a future 'Registration begins/opens' badge")

    if not_full and not final:
        problems.append(
            f"{len(not_full)} age-eligible, non-FULL program(s) exist but NONE survived the "
            "registration filter — this is the original bug's signature.")

    if problems:
        print()
        for msg in problems:
            print(f"  FAIL {msg}")
        return 1
    print("\n  All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
