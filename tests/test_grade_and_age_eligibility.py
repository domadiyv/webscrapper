"""Tests for the age/grade eligibility rules verified against the live portal.

The portal restricts a program by age *or* by grade: a grade-based program leaves
Ages as "- Not specified", and vice versa. Every expectation below was confirmed
by querying the portal's own FilterPrograms `Age` filter on 2026-09-15.
"""
import pytest

from recdesk_scraper.age import (
    age_includes,
    grade_age_range,
    grade_bounds,
    grade_includes,
    has_age_info,
)
from recdesk_scraper.parser import age_eligible


# --------------------------------------------------------------------------
# A lone age is a MINIMUM, not an exact match.
# Portal evidence: programId 6021 ("18y", titled "Bethune Center 18+") is
# returned when filtering for ages 18, 19, 25, 40 and 50 — but not 17.
# programId 6046 ("40y") is returned at 40 and 50, but not 25.
# When the portal means a single age it writes a range instead: "8y - 8y".
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cell,target,expected", [
    ("18y", 17, False),
    ("18y", 18, True),
    ("18y", 19, True),
    ("18y", 25, True),
    ("18y", 50, True),
    ("40y", 25, False),
    ("40y", 40, True),
    ("40y", 50, True),
    # A genuine single-age program is rendered as a range and stays exact.
    ("8y - 8y", 8, True),
    ("8y - 8y", 9, False),
])
def test_lone_age_is_a_minimum(cell, target, expected):
    assert age_includes(cell, target) is expected


# --------------------------------------------------------------------------
# has_age_info — the portal's placeholder is "- Not specified", never "-".
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cell,expected", [
    ("7y - 14y", True),
    ("18y", True),
    ("Ages 12+", True),
    ("- Not specified", False),
    ("N/A", False),
    ("-", False),
    ("", False),
])
def test_has_age_info(cell, expected):
    assert has_age_info(cell) is expected


# --------------------------------------------------------------------------
# Grade -> age mapping. A child in grade N is age N+5 to N+6.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cell,bounds,ages", [
    ("2 - 4",           (2, 4),   (7, 10)),
    ("Grades 2 - 4",    (2, 4),   (7, 10)),
    ("5 - 6",           (5, 6),   (10, 12)),
    ("9 - 10",          (9, 10),  (14, 16)),
    ("11 - 12",         (11, 12), (16, 18)),
    ("3",               (3, 3),   (8, 9)),
    ("K - 2",           (0, 2),   (5, 8)),
    ("Kindergarten - 1",(0, 1),   (5, 7)),
    ("Pre-K - K",       (-1, 0),  (4, 6)),
    ("2nd - 4th",       (2, 4),   (7, 10)),
    ("- Not specified", None,     None),
    ("N/A",             None,     None),
    ("",                None,     None),
])
def test_grade_bounds_and_age_range(cell, bounds, ages):
    assert grade_bounds(cell) == bounds
    assert grade_age_range(cell) == ages


@pytest.mark.parametrize("cell,target,expected", [
    ("2 - 4", 8, True),      # the program the scraper used to miss
    ("2 - 4", 7, True),
    ("2 - 4", 10, True),
    ("2 - 4", 11, False),
    ("5 - 6", 8, False),
    ("11 - 12", 8, False),
    ("- Not specified", 8, False),
])
def test_grade_includes(cell, target, expected):
    assert grade_includes(cell, target) is expected


# --------------------------------------------------------------------------
# age_eligible — the single decision production and the audit share.
# --------------------------------------------------------------------------

def _prog(ages="- Not specified", grades="- Not specified"):
    return {"Age / Age Range": ages, "Grade(s)": grades}


def test_age_cell_wins_when_present():
    ok, why = age_eligible(_prog(ages="7y - 14y", grades="11 - 12"), 8)
    assert ok is True
    assert "ages" in why


def test_falls_back_to_grades_when_age_unspecified():
    """programId 5985 — "Back 2 School 3v3 BB | Grades 2-4", open with 11 spots.

    This is the program the scraper silently dropped: the portal returns it when
    filtering for age 8, but its Ages cell reads "- Not specified".
    """
    ok, why = age_eligible(_prog(grades="2 - 4"), 8)
    assert ok is True
    assert "grades" in why and "7-10" in why


@pytest.mark.parametrize("grades,target,expected", [
    ("2 - 4", 8, True),
    ("5 - 6", 8, False),     # 10-12
    ("7 - 8", 8, False),     # 12-14
    ("9 - 10", 8, False),    # 14-16
    ("11 - 12", 8, False),   # 16-18
])
def test_grade_based_programs_filter_by_age(grades, target, expected):
    assert age_eligible(_prog(grades=grades), target)[0] is expected


def test_no_age_and_no_grade_is_open_to_everyone():
    """The portal returns unrestricted programs at every age, so we do too."""
    for target in (4, 8, 15, 40):
        ok, why = age_eligible(_prog(), target)
        assert ok is True
        assert "no age or grade restriction" in why


def test_n_a_placeholders_are_treated_as_unrestricted():
    ok, _ = age_eligible(_prog(ages="N/A", grades="N/A"), 8)
    assert ok is True
