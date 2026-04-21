"""Tests for extract_age_from_name — title fallback when Ages cell is missing."""
import pytest
from scraper import extract_age_from_name


CASES = [
    # name, expected non-empty fragment that contains an age phrase
    ("2026 Spring - Boxing @ MS# 7 Ages 7-11 (Mon/Wed)",            "Ages 7-11"),
    ("RHYTHM & ROOTS - @ Pershing Field CC Ages 8 to 18 Wednesdays", "Ages 8 to 18"),
    ("2026 Spring - Badminton @ Kotofit    Ages 7 to 14",            "Ages 7 to 14"),
    ("2026 Flag Football - Flag Football @ Franco Field. Ages 7-9",  "Ages 7-9"),
    ("2026 Spring - Safe Sitter Essentials @ PF Comm. Center Ages 12+", "Ages 12+"),
    ("Sensei Darren's - BULLY PROOF PROGRAM @PS#41 Ages 7 to 14",     "Ages 7 to 14"),
    ("2026 Spring - Tennis Beginners - Ages 6-10 (Mon)",              "Ages 6-10"),
    ("2026 Spring - Track- Lincoln Park Ages 5-9 (Mon/Wed)",          "Ages 5-9"),
    ("2026 - Legends Summer Camp Week 1 & 2",                          ""),
    ("Blue Dolphin Book Club P.S. 20 Students ONLY",                   ""),
]


@pytest.mark.parametrize("name,expected_substr", CASES)
def test_extract_age_from_name(name, expected_substr):
    got = extract_age_from_name(name)
    if expected_substr == "":
        assert got == ""
    else:
        assert expected_substr.lower().replace(" ", "") in got.lower().replace(" ", ""), \
            f"From {name!r} got {got!r}, expected substring {expected_substr!r}"
