"""BeautifulSoup-based parser for FilterPrograms HTML responses."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .age import age_includes, extract_age_from_name
from .config import TARGET_AGE

COLUMNS = [
    "Program Name", "Category", "Age / Age Range",
    "Date(s)", "Day(s)", "Opening", "Remaining",
]


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


def parse_programs_html(html: str, target_age: int = TARGET_AGE) -> list[dict]:
    """Parse a FilterPrograms HTML response and return matching programs."""
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

            detail_tr = None
            j = i + 1
            while j < len(children):
                next_tr = children[j]
                ncls = " ".join(next_tr.get("class", []))
                if "sub-category-header" in ncls or next_tr.find("td", class_="category-header"):
                    break
                if "hidden-xs" in ncls:
                    detail_tr = next_tr
                    break
                j += 1

            ages = dates = days = opening = remaining = ""
            if detail_tr is not None:
                dates = _cell_value_after_label(detail_tr, "Dates")
                days = _cell_value_after_label(detail_tr, "Days")
                ages = _cell_value_after_label(detail_tr, "Ages")
                opening = _cell_value_after_label(detail_tr, "Openings")
                remaining = _cell_value_after_label(detail_tr, "Remaining")

            if not ages or ages.strip() in {"-", "N/A"}:
                ages = extract_age_from_name(name) or ages

            if age_includes(ages, target_age):
                results.append({
                    "Program Name": name,
                    "Category": current_category,
                    "Age / Age Range": ages or "N/A",
                    "Date(s)": dates or "N/A",
                    "Day(s)": days or "N/A",
                    "Opening": opening or "N/A",
                    "Remaining": remaining or "N/A",
                })
        i += 1

    return results


def has_next_page(html: str, current_page: int) -> bool:
    """Return True if pagination links to a page > current_page."""
    soup = BeautifulSoup(html, "html.parser")
    pagination = soup.select_one("ul.pagination, .pagination")
    if not pagination:
        return False
    nums = [
        int(_clean(a.get_text())) for a in pagination.find_all("a")
        if _clean(a.get_text()).isdigit()
    ]
    return bool(nums) and max(nums) > current_page
