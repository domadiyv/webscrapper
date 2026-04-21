"""Tests for age_includes — covers every age format observed on the live portal."""
import pytest
from scraper import age_includes


# --- Formats observed in the Ages cell of the FilterPrograms HTML ---
PORTAL_AGE_CELLS = [
    ("7y - 14y",  True),
    ("8y - 8y",   True),
    ("8y - 11y",  True),
    ("6y - 14y",  True),
    ("6y - 8y",   True),
    ("5y - 9y",   True),
    ("7y - 9y",   True),
    ("6y - 10y",  True),
    ("12y - 14y", False),
    ("9y - 11y",  False),
    ("4y - 6y",   False),
    ("4y - 5y",   False),
    ("1y - 3y",   False),
    ("15y - 99y", False),
    ("11y - 14y", False),
    ("11y - 12y", False),
    ("13y - 16y", False),
    ("12y - 15y", False),
]


# --- Formats observed in program titles (fallback when Ages cell is empty) ---
PORTAL_NAME_AGE_FRAGMENTS = [
    ("Ages 7 to 14",  True),
    ("Ages 7-8",      True),
    ("Ages 8 to 18",  True),         # RHYTHM & ROOTS
    ("Ages 7-11",     True),         # Boxing @ MS#7
    ("Ages 12-14",    False),        # Boxing 12-14
    ("Ages 7-9",      True),         # Flag Football
    ("Ages 7 - 14",   True),
    ("Ages 8-11",     True),         # Soccer Ball Mastery
    ("Ages 6-8",      True),         # Soccer Shoot 4 the Stars
    ("Ages 12+",      False),        # Safe Sitter
    ("Ages 4-6",      False),
    ("Ages 5-7",      False),
    ("Ages 9 -11",    False),
    ("Ages 9 - 11",   False),
    ("Ages 12 - 14",  False),
    ("Ages 10 -13",   False),
    ("Ages 7 to 15",  True),
    ("Ages 15-24",    False),
]


# --- Edge-case formats not directly seen but likely to appear ---
EDGE_CASE_FORMATS = [
    ("8+",            True),
    ("8 and up",      True),
    ("8 & up",        True),
    ("8 or older",    True),
    ("9+",            False),
    ("8",             True),
    ("9",             False),
    ("Ages: 6-9",     True),
    ("AGES 7-10",     True),         # uppercase
    ("ages 7–10",     True),         # en dash
    ("ages 7—10",     True),         # em dash
    ("",              False),
    ("N/A",           False),
    ("-",             False),
]


@pytest.mark.parametrize("text,expected", PORTAL_AGE_CELLS)
def test_portal_age_cell_formats(text, expected):
    assert age_includes(text, 8) is expected, f"{text!r} expected {expected}"


@pytest.mark.parametrize("text,expected", PORTAL_NAME_AGE_FRAGMENTS)
def test_portal_name_age_fragments(text, expected):
    assert age_includes(text, 8) is expected, f"{text!r} expected {expected}"


@pytest.mark.parametrize("text,expected", EDGE_CASE_FORMATS)
def test_edge_case_formats(text, expected):
    assert age_includes(text, 8) is expected, f"{text!r} expected {expected}"


def test_target_age_parameter():
    """Different target ages exercise the full range logic."""
    assert age_includes("6y - 9y", 6) is True
    assert age_includes("6y - 9y", 9) is True
    assert age_includes("6y - 9y", 5) is False
    assert age_includes("6y - 9y", 10) is False
