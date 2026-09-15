"""Age/grade parsing for the Ages cell, the Grades cell, and program-name fallbacks."""
from __future__ import annotations

import re

from .config import TARGET_AGE

# A child in grade N is typically this many years old during the school year:
# kindergarten (grade 0) is 5-6, grade 2 is 7-8, grade 12 is 17-18.
GRADE_AGE_OFFSET_LOW = 5
GRADE_AGE_OFFSET_HIGH = 6

_GRADE_TOKENS = {"pk": -1, "k": 0}


def has_age_info(age_text: str) -> bool:
    """True if the Ages cell carries a usable age.

    The portal renders "- Not specified" (not "-" or an empty cell) when a
    program has no age restriction, so emptiness alone is not the test.
    """
    return bool(age_text) and any(ch.isdigit() for ch in age_text)


def age_includes(age_text: str, target: int = TARGET_AGE) -> bool:
    """Return True if `age_text` covers `target` age.

    Handles forms seen on the live portal:
      "7y - 14y", "8y - 8y", "Ages 7-11", "Ages 8 to 18",
      "Ages 12+", "8 and up", "8 & up", "8 or older",
      single number "18y", "Ages: 7-9".

    A lone age is a **minimum**, not an exact match: the portal writes "18y" for
    a program titled "18+", and returns it when filtering for ages 18 through 50.
    When it means exactly one age it writes a range — "8y - 8y".
    """
    if not age_text:
        return False
    text = age_text.strip().lower()
    text = re.sub(r"^ages?\s*:?\s*", "", text)
    text = text.replace("y", " ")

    m = re.search(r"(\d+)\s*(?:[-–—]|to)\s*(\d+)", text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return lo <= target <= hi

    m = re.search(r"(\d+)\s*(?:\+|&\s*up|and\s*up|or\s*older|or\s*up)", text)
    if m:
        return int(m.group(1)) <= target

    m = re.fullmatch(r"\s*(\d+)\s*", text)
    if m:
        return int(m.group(1)) <= target

    nums = [int(n) for n in re.findall(r"\d+", text)]
    if len(nums) == 1:
        return nums[0] <= target
    if len(nums) >= 2:
        return min(nums) <= target <= max(nums)
    return False


def grade_bounds(grade_text: str) -> tuple[int, int] | None:
    """Parse the Grades cell into (lowest, highest) grade numbers.

    Kindergarten is 0 and pre-K is -1, so "K - 2" is (0, 2). Returns None when
    the cell carries no grade — the portal's "- Not specified", or an empty cell.
    """
    if not grade_text:
        return None
    text = grade_text.strip().lower()
    text = re.sub(r"^grades?\s*:?\s*", "", text)
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"^-\s*", "", text)          # portal renders "- Not specified"
    if not text or "not specified" in text:
        return None
    # Collapse pre-K/kindergarten to single tokens before splitting on the dash,
    # so "pre-k" is not torn in half by the range separator.
    text = re.sub(r"pre[-\s]*k(?:indergarten)?", "pk", text)
    text = re.sub(r"kindergarten", "k", text)

    nums = []
    for part in re.split(r"\s*(?:-|to|through)\s*", text):
        part = part.strip()
        if not part:
            continue
        if part in _GRADE_TOKENS:
            nums.append(_GRADE_TOKENS[part])
            continue
        m = re.fullmatch(r"(\d+)(?:st|nd|rd|th)?", part)
        if m:
            nums.append(int(m.group(1)))
    return (min(nums), max(nums)) if nums else None


def grade_age_range(grade_text: str) -> tuple[int, int] | None:
    """The age span a Grades cell corresponds to, or None if it carries no grade."""
    bounds = grade_bounds(grade_text)
    if bounds is None:
        return None
    lo, hi = bounds
    return lo + GRADE_AGE_OFFSET_LOW, hi + GRADE_AGE_OFFSET_HIGH


def grade_includes(grade_text: str, target: int = TARGET_AGE) -> bool:
    """True if a child aged `target` is in the grade range the cell names."""
    span = grade_age_range(grade_text)
    if span is None:
        return False
    return span[0] <= target <= span[1]


def extract_age_from_name(name: str) -> str:
    """Pull an age phrase out of a program name (fallback when Ages cell empty)."""
    if not name:
        return ""
    m = re.search(
        r"ages?\s*[:\-]?\s*\d+\s*(?:[-–—to]+\s*\d+|\+|&\s*up|and\s*up|or\s*older)?",
        name,
        re.IGNORECASE,
    )
    return m.group(0).strip() if m else ""
