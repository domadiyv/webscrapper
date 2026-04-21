"""End-to-end parse tests against real HTML captured from the live portal.

The fixtures probe_filter_page1.html .. probe_filter_page3.html are the actual
responses returned by https://jcrec.recdesk.com/Community/Program/FilterPrograms.
"""
from pathlib import Path

import pytest

from scraper import parse_programs_html, has_next_page

FIXTURES_DIR = Path(__file__).resolve().parent.parent
PAGES = [FIXTURES_DIR / f"probe_filter_page{i}.html" for i in (1, 2, 3)]


def _all_programs():
    out, seen = [], set()
    for p in PAGES:
        html = p.read_text(encoding="utf-8")
        for prog in parse_programs_html(html, target_age=8):
            key = (prog["Program Name"], prog["Date(s)"], prog["Day(s)"])
            if key in seen:
                continue
            seen.add(key)
            out.append(prog)
    return out


@pytest.fixture(scope="module")
def all_programs():
    for p in PAGES:
        if not p.exists():
            pytest.skip(f"fixture missing: {p}")
    return _all_programs()


# ---------------------------------------------------------------------------
# Programs that MUST be in the age-8 result set (manually verified from portal)
# ---------------------------------------------------------------------------

EXPECTED_PRESENT = [
    # (substring of program name, expected category, expected age range substring)
    ("RHYTHM & ROOTS",                     "Music",         "8 to 18"),
    ("Boxing @ MS# 7 Ages 7-11 (Mon/Wed)",  "Boxing",       "7-11"),
    ("Boxing @ MS# 7 Ages 7-11 (Tue/Thu)",  "Boxing",       "7-11"),
    ("Badminton @ Kotofit",                 "Badminton",    "7"),
    ("Basketball @ Bayside Park Ages 7-8 (Fridays)", "Basketball", "7"),
    ("Break Dancing",                       "Dance",        "7"),
    ("Lacrosse @ PS # 26",                  "Lacrosse",     "7"),
    ("Soccer Ball Mastery @ Gateway Field Ages 8-11", "Soccer", "8"),
    ("Shoot 4 the Stars @ Martucci Ages 6-8", "Soccer",     "6"),
    ("Tennis Beginners - Ages 6-10",        "Tennis",       "6"),
    ("Tennis Advanced - Ages 6-10",         "Tennis",       "6"),
    ("Track- Lincoln Park Ages 5-9 (Mon/Wed)", "Track and Field", "5"),
    ("JC Rise Summer Camp: North-Session 1", "Summer Camp (JC Rise)", "6"),
    ("Pershing Swim Class LTS 1 Sunday",     "Swim",        "6"),
    ("Co-Ed Select - Advanced Soccer 2017-18", "Travel Soccer", "7"),
]


# Programs that MUST NOT appear (age does not include 8)
EXPECTED_ABSENT = [
    "Ages 12-14",       # Boxing 12-14, Basketball 12-14
    "Ages 15-24",
    "Ages 12+",         # Safe Sitter
    "Adult1",           # Swim Adult
    "Baby&Me",          # Swim 1-3y
    "PSA 1",            # Swim 4-5y
    "PSA2",
    "Biddy",            # Basketball 4-6
    "2010 (Tues/Thurs)", # Travel Soccer 13-16
]


def test_returns_at_least_30_programs(all_programs):
    """The portal currently has 35-ish age-8 programs across 3 pages."""
    assert len(all_programs) >= 30, f"only got {len(all_programs)}"


def test_each_program_has_all_required_columns(all_programs):
    required = {"Program Name", "Category", "Age / Age Range",
                "Date(s)", "Day(s)", "Opening", "Remaining"}
    for p in all_programs:
        assert required.issubset(p.keys()), f"missing keys in {p}"
        assert p["Program Name"] != "N/A", f"name missing: {p}"


def test_no_duplicates(all_programs):
    keys = [(p["Program Name"], p["Date(s)"], p["Day(s)"]) for p in all_programs]
    assert len(keys) == len(set(keys)), "duplicate program rows present"


@pytest.mark.parametrize("name_substr,category,age_substr", EXPECTED_PRESENT)
def test_expected_program_present(all_programs, name_substr, category, age_substr):
    matches = [p for p in all_programs if name_substr.lower() in p["Program Name"].lower()]
    assert matches, f"expected program containing {name_substr!r} not found. " \
                    f"All names: {[p['Program Name'] for p in all_programs]}"
    p = matches[0]
    assert category.lower() in p["Category"].lower(), \
        f"category mismatch for {name_substr}: got {p['Category']!r}"


@pytest.mark.parametrize("forbidden_substr", EXPECTED_ABSENT)
def test_expected_program_absent(all_programs, forbidden_substr):
    bad = [p for p in all_programs if forbidden_substr.lower() in p["Program Name"].lower()]
    assert not bad, f"program(s) that should be filtered out present: " \
                    f"{[p['Program Name'] for p in bad]}"


def test_dates_present_for_most_programs(all_programs):
    """At least 80% should have a parsed Date(s) value."""
    with_dates = sum(1 for p in all_programs if p["Date(s)"] != "N/A")
    assert with_dates >= 0.8 * len(all_programs), \
        f"only {with_dates}/{len(all_programs)} have dates"


def test_categories_match_real_portal(all_programs):
    cats = {p["Category"] for p in all_programs}
    expected_some_of = {"Boxing", "Music", "Soccer", "Swim", "Tennis", "Badminton"}
    assert cats & expected_some_of, f"no recognised categories in {cats}"


# ---------------------------------------------------------------------------
# Pagination detector
# ---------------------------------------------------------------------------

def test_has_next_page_detects_pagination():
    p1 = PAGES[0].read_text(encoding="utf-8")
    p3 = PAGES[2].read_text(encoding="utf-8")
    assert has_next_page(p1, 1) is True   # page 1 → there's a 2 and a 3
    assert has_next_page(p1, 2) is True   # page 2 still has a 3
    assert has_next_page(p3, 3) is False  # page 3 → no further pages
