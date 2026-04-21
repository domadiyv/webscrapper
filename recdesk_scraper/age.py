"""Age-range parsing for both the Ages cell and program-name fallbacks."""
from __future__ import annotations

import re

from .config import TARGET_AGE


def age_includes(age_text: str, target: int = TARGET_AGE) -> bool:
    """Return True if `age_text` covers `target` age.

    Handles forms seen on the live portal:
      "7y - 14y", "8y - 8y", "Ages 7-11", "Ages 8 to 18",
      "Ages 12+", "8 and up", "8 & up", "8 or older",
      single number "8", "Ages: 7-9".
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
        return int(m.group(1)) == target

    nums = [int(n) for n in re.findall(r"\d+", text)]
    if len(nums) == 1:
        return nums[0] == target
    if len(nums) >= 2:
        return min(nums) <= target <= max(nums)
    return False


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
