"""BeautifulSoup-based parser for FilterPrograms HTML responses."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .age import (
    age_includes,
    extract_age_from_name,
    grade_age_range,
    grade_bounds,
    has_age_info,
)
from .config import TARGET_AGE

COLUMNS = [
    "Program Name", "Category", "Age / Age Range", "Grade(s)",
    "Date(s)", "Day(s)", "Opening", "Remaining", "URL", "Registration Status",
]

PORTAL_ORIGIN = "https://jcrec.recdesk.com"

# Registration states derived from the portal markup.
STATE_OPEN = "open"          # "Register Now" button — registerable right now
STATE_UPCOMING = "upcoming"  # badge "Registration begins/opens on <date>"
STATE_WAITLIST = "waitlist"  # "Wait List" button — full but joinable
STATE_ENDED = "ended"        # badge "Registration ended/closed on <date>"
STATE_OFFLINE = "offline"    # badge "No online registration"
STATE_FULL = "full"          # no badge, no button, Remaining shows FULL
STATE_UNKNOWN = "unknown"    # nothing recognisable — markup probably changed


def _is_full(remaining: str) -> bool:
    return "full" in (remaining or "").lower()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _cell_value_after_label(tr, label: str) -> str:
    for td in tr.find_all("td", recursive=False):
        head = td.find(class_="text-semibold")
        if head and _clean(head.get_text()).lower() == label.lower():
            small = td.find("small")
            if small:
                return _clean(small.get_text(" ", strip=True))
            return _clean(td.get_text(" ", strip=True).removeprefix(label).strip())
    return ""


def _registration_badge(tr) -> str:
    """Text of the status badge row, e.g. 'Registration ended on 4/3/2026'.

    The portal only renders this row for non-default states; a program that is
    simply open for registration has no badge at all.
    """
    badge = tr.find("div", class_="label")
    if badge:
        text = _clean(badge.get_text(" ", strip=True))
        if text:
            return text
    text = _clean(tr.get_text(" ", strip=True))
    return text if "registration" in text.lower() else ""


def _action_label(detail_tr) -> str:
    """Text of the action button in the trailing cell ('Register Now' / 'Wait List')."""
    if detail_tr is None:
        return ""
    button = detail_tr.find("button")
    if button:
        return _clean(button.get_text(" ", strip=True))
    return ""


def _classify_registration(badge: str, action: str, remaining: str = "") -> tuple[str, str]:
    """Return (state, human-readable status) for a program.

    `badge` is the status-badge text (may be empty), `action` the button label,
    `remaining` the Remaining cell. Only `unknown` means "markup not recognised".
    """
    low = badge.lower()
    if badge:
        if "begin" in low or "open" in low or "start" in low:
            return STATE_UPCOMING, badge
        if "end" in low or "close" in low:
            return STATE_ENDED, badge
        if "no online registration" in low:
            return STATE_OFFLINE, badge

    action_low = action.lower()
    if "register" in action_low:
        return STATE_OPEN, "Registration open"
    if "wait list" in action_low or "waitlist" in action_low:
        return STATE_WAITLIST, "Wait list only"

    # Full with no waitlist button: the portal renders an empty action cell.
    if _is_full(remaining):
        return STATE_FULL, "Full"

    return (STATE_UNKNOWN, badge) if badge else (STATE_UNKNOWN, "")


def extract_programs(html: str) -> list[dict]:
    """Every program row on the page, with no age/FULL filtering applied.

    `parse_programs_html` filters this. Audit tooling uses it directly so that
    what it reports is the same extraction production actually runs.
    """
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.select_one("table.table-vcenter > tbody")
    if not tbody:
        return []

    results: list[dict] = []
    current_category = "N/A"

    children = list(tbody.find_all("tr", recursive=False))
    i = 0
    while i < len(children):
        tr = children[i]

        cat_td = tr.find("td", class_="category-header")
        if cat_td:
            strong = cat_td.find("strong")
            if strong:
                current_category = _clean(strong.get_text())
            i += 1
            continue

        cls = " ".join(tr.get("class", []))
        if "sub-category-header" in cls:
            link = tr.find("a", href=re.compile(r"programId="))
            name = _clean(link.get_text()) if link else "N/A"
            href = link.get("href", "") if link else ""
            url = (PORTAL_ORIGIN + href) if href.startswith("/") else (href or "")

            # Scan the whole block belonging to this program. The badge row sits
            # between the name row and the detail row, so we must not stop at the
            # first `hidden-xs` row before having looked at everything.
            detail_tr = None
            badge = ""
            j = i + 1
            while j < len(children):
                next_tr = children[j]
                ncls = " ".join(next_tr.get("class", []))
                if "sub-category-header" in ncls or next_tr.find("td", class_="category-header"):
                    break
                if "hidden-xs" in ncls:
                    if detail_tr is None:
                        detail_tr = next_tr
                elif "visible-xs" not in ncls and not badge:
                    badge = _registration_badge(next_tr)
                j += 1

            ages = grades = dates = days = opening = remaining = ""
            if detail_tr is not None:
                dates = _cell_value_after_label(detail_tr, "Dates")
                days = _cell_value_after_label(detail_tr, "Days")
                ages = _cell_value_after_label(detail_tr, "Ages")
                grades = _cell_value_after_label(detail_tr, "Grades")
                opening = _cell_value_after_label(detail_tr, "Openings")
                remaining = _cell_value_after_label(detail_tr, "Remaining")

            state, reg_status = _classify_registration(
                badge, _action_label(detail_tr), remaining)

            # The portal writes "- Not specified" for an unrestricted age, so
            # test for a usable age rather than for an empty-looking cell, and
            # normalise its placeholder to the "N/A" used everywhere else.
            if not has_age_info(ages):
                ages = extract_age_from_name(name) or ""
            if grade_bounds(grades) is None:
                grades = ""

            results.append({
                    "Program Name": name,
                    "Category": current_category,
                    "Age / Age Range": ages or "N/A",
                    "Grade(s)": grades or "N/A",
                    "Date(s)": dates or "N/A",
                    "Day(s)": days or "N/A",
                    "Opening": opening or "N/A",
                    "Remaining": remaining or "N/A",
                    "URL": url or "N/A",
                    "Registration Status": reg_status or "N/A",
                    # Not part of COLUMNS — used for filtering, dropped from output.
                    "Registration State": state,
                    "Program Id": re.search(r"programId=(\d+)", href).group(1) if href and re.search(r"programId=(\d+)", href) else "",
            })
        i += 1

    return results


def age_eligible(program: dict, target_age: int = TARGET_AGE) -> tuple[bool, str]:
    """Return (eligible, reason) for one program at `target_age`.

    The portal restricts a program by age *or* by grade, never reliably by both:
    a grade-based program leaves Ages as "- Not specified" and vice versa. Its own
    age filter honours all three cases, so matching on the Ages cell alone silently
    drops every grade-based program. Precedence:

    1. a usable Ages cell (including one recovered from the program title),
    2. otherwise the Grades cell, mapped to the ages that attend those grades,
    3. otherwise the program carries no age restriction and is open to anyone —
       which is how the portal itself treats it.

    Production and `scripts/verify_live.py` both call this, so the audit cannot
    drift from the filtering that actually runs.
    """
    ages = program.get("Age / Age Range", "")
    if has_age_info(ages):
        return age_includes(ages, target_age), f"ages {ages!r}"

    grades = program.get("Grade(s)", "")
    span = grade_age_range(grades)
    if span is not None:
        lo, hi = span
        return lo <= target_age <= hi, f"grades {grades!r} -> ages {lo}-{hi}"

    return True, "no age or grade restriction"


def parse_programs_html(html: str, target_age: int = TARGET_AGE) -> list[dict]:
    """Parse a FilterPrograms HTML response and return age-matching, non-FULL programs."""
    return [
        p for p in extract_programs(html)
        if age_eligible(p, target_age)[0] and not _is_full(p["Remaining"])
    ]


def has_next_page(html: str, current_page: int) -> bool:
    """Return True if there is a page after `current_page`.

    Prefers the pager's own "next" control, which stays correct even when the
    portal renders a windowed page list (1 2 3 … 9) rather than every number.
    """
    soup = BeautifulSoup(html, "html.parser")
    pagination = soup.select_one("ul.pagination, .pagination")
    if not pagination:
        return False

    next_link = pagination.find(id="next") or pagination.find(class_="page-next")
    if next_link is not None:
        parent_classes = " ".join(next_link.parent.get("class", [])) if next_link.parent else ""
        disabled = (
            "disabled" in parent_classes
            or "disabled" in " ".join(next_link.get("class", []))
            or str(next_link.get("aria-disabled", "")).lower() == "true"
        )
        return not disabled

    nums = [
        int(_clean(a.get_text())) for a in pagination.find_all("a")
        if _clean(a.get_text()).isdigit()
    ]
    return bool(nums) and max(nums) > current_page
