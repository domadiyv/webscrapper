"""RecDesk community-programs scraper."""
from .age import age_includes, extract_age_from_name, grade_includes
from .parser import COLUMNS, parse_programs_html, has_next_page, age_eligible
from .exporter import save_excel
from .fetcher import fetch_all_html_pages
from .mailer import send_email

__all__ = [
    "age_includes",
    "extract_age_from_name",
    "grade_includes",
    "age_eligible",
    "COLUMNS",
    "parse_programs_html",
    "has_next_page",
    "save_excel",
    "fetch_all_html_pages",
    "send_email",
]
