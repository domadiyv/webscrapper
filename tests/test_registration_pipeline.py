"""Regression tests for the stages that run *after* parse_programs_html.

These cover `_dedupe` and `_filter_new_registrations` in `__main__`, which had no
test coverage. A bug there silenced the whole report while the parser tests — which
call parse_programs_html directly — stayed green.
"""
from pathlib import Path

import pytest

from recdesk_scraper.__main__ import _dedupe, _filter_new_registrations
from recdesk_scraper.parser import (
    STATE_ENDED,
    STATE_FULL,
    STATE_OFFLINE,
    STATE_OPEN,
    STATE_UPCOMING,
    STATE_WAITLIST,
    _classify_registration,
    parse_programs_html,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PAGES = [FIXTURES_DIR / f"probe_filter_page{i}.html" for i in (1, 2, 3)]


@pytest.fixture(scope="module")
def parsed():
    for p in PAGES:
        if not p.exists():
            pytest.skip(f"fixture missing: {p}")
    out = []
    for p in PAGES:
        out.extend(parse_programs_html(p.read_text(encoding="utf-8"), target_age=8))
    return out


# --------------------------------------------------------------------------
# Registration state classification
# --------------------------------------------------------------------------

@pytest.mark.parametrize("badge,action,remaining,expected", [
    # The portal renders NO badge for an open program — only the button.
    ("",                                 "Register Now",               "24",   STATE_OPEN),
    ("",                                 "Wait List (opens a dialog)", "FULL", STATE_WAITLIST),
    ("Registration begins on 4/22/2026", "",                           "20",   STATE_UPCOMING),
    ("Registration opens on 4/22/2026",  "",                           "20",   STATE_UPCOMING),
    ("Registration ended on 4/3/2026",   "",                           "12",   STATE_ENDED),
    ("No online registration",           "",                           "8",    STATE_OFFLINE),
    # Full with no waitlist button — an empty action cell, not a parse failure.
    ("",                                 "",                           "FULL", STATE_FULL),
    # Nothing recognisable at all -> unknown, which the audit treats as a red flag.
    ("",                                 "",                           "10",   "unknown"),
])
def test_classify_registration(badge, action, remaining, expected):
    state, _ = _classify_registration(badge, action, remaining)
    assert state == expected, f"{badge!r}/{action!r}/{remaining!r} -> {state!r}"


def test_open_programs_get_a_state_not_a_blank_status(parsed):
    """The original bug: open programs carried no status text and were dropped."""
    opens = [p for p in parsed if p["Registration State"] == STATE_OPEN]
    assert opens, "no open programs parsed from fixtures"
    for p in opens:
        assert p["Registration Status"] == "Registration open"


def test_every_program_carries_a_state(parsed):
    for p in parsed:
        assert p.get("Registration State"), f"no state for {p['Program Name']}"
        assert p.get("Program Id"), f"no programId for {p['Program Name']}"


# --------------------------------------------------------------------------
# The filter must not discard currently-open programs
# --------------------------------------------------------------------------

def test_filter_keeps_open_programs(parsed):
    kept = _filter_new_registrations(_dedupe(parsed))
    assert len(kept) >= 10, (
        f"registration filter kept only {len(kept)} program(s); "
        "open-now programs are being discarded again"
    )
    assert any(p["Registration State"] == STATE_OPEN for p in kept)


def test_filter_drops_ended_registrations(parsed):
    kept = _filter_new_registrations(_dedupe(parsed))
    for p in kept:
        assert p["Registration State"] not in (STATE_ENDED, STATE_OFFLINE), \
            f"{p['Program Name']} should not be reported ({p['Registration Status']})"


def test_lacrosse_with_ended_registration_is_filtered_out(parsed):
    """Fixture page 1 has a Lacrosse program whose registration already ended."""
    ended = [p for p in parsed
             if "Lacrosse @ PS # 26" in p["Program Name"]]
    assert ended and ended[0]["Registration State"] == STATE_ENDED
    kept = _filter_new_registrations(_dedupe(parsed))
    assert not [p for p in kept if "Lacrosse @ PS # 26" in p["Program Name"]]


# --------------------------------------------------------------------------
# Dedupe must key on programId, not (name, dates, days)
# --------------------------------------------------------------------------

def test_dedupe_keeps_distinct_sections_sharing_name_dates_days(parsed):
    """Two 'Bucket Drumming (Mon)' sections share name/dates/days but are distinct."""
    drumming = [p for p in parsed if "Bucket Drumming" in p["Program Name"]]
    assert len(drumming) == 2, f"fixture changed: {len(drumming)} drumming rows"
    assert len({p["Program Id"] for p in drumming}) == 2

    kept = _dedupe(parsed)
    still = [p for p in kept if "Bucket Drumming" in p["Program Name"]]
    assert len(still) == 2, "dedupe collapsed two distinct programIds into one"


def test_dedupe_removes_true_repeats(parsed):
    doubled = parsed + parsed
    assert len(_dedupe(doubled)) == len(_dedupe(parsed))


def test_dedupe_preserves_every_program_id(parsed):
    kept = _dedupe(parsed)
    assert {p["Program Id"] for p in kept} == {p["Program Id"] for p in parsed}


# --------------------------------------------------------------------------
# Pagination must survive a windowed pager
# --------------------------------------------------------------------------

def _pager(page_links: str) -> str:
    return f'<table class="table-vcenter"><tbody></tbody></table><ul class="pagination">{page_links}</ul>'


def test_has_next_page_uses_next_control_on_windowed_pager():
    """A windowed pager shows only nearby numbers; max-number logic stops early."""
    from recdesk_scraper.parser import has_next_page
    # On page 5 of many, the pager may only render 3..7 — but "next" is live.
    html = _pager(
        '<li><a class="page-selector" data-page="3">3</a></li>'
        '<li><a class="page-selector" data-page="4">4</a></li>'
        '<li class="active"><a class="page-selector" data-page="5">5</a></li>'
        '<li><a id="next" class="page-next">&raquo;</a></li>'
    )
    assert has_next_page(html, 5) is True


def test_has_next_page_false_when_next_disabled():
    from recdesk_scraper.parser import has_next_page
    html = _pager(
        '<li><a class="page-selector" data-page="1">1</a></li>'
        '<li class="disabled"><a id="next" aria-disabled="true">&raquo;</a></li>'
    )
    assert has_next_page(html, 1) is False
