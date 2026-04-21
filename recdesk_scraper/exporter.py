"""Sort programs and write them to a timestamped Excel file."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import OUTPUT_DIR, TARGET_AGE
from .parser import COLUMNS

log = logging.getLogger(__name__)

_DATE_FORMATS = (
    "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d",
    "%b %d, %Y", "%B %d, %Y", "%m/%d/%y",
)


def date_sort_key(date_str: str) -> datetime:
    if not date_str or date_str == "N/A":
        return datetime.max
    first = re.split(r"\s*[-–]\s*", date_str)[0].strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(first, fmt)
        except ValueError:
            continue
    return datetime.max


def save_excel(programs: list[dict]) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    df = pd.DataFrame(programs, columns=COLUMNS)
    if not df.empty:
        df["_sort"] = df["Date(s)"].apply(date_sort_key)
        df.sort_values(["_sort", "Program Name"], inplace=True)
        df.drop(columns=["_sort"], inplace=True)
        df.reset_index(drop=True, inplace=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"programs_age{TARGET_AGE}_{timestamp}.xlsx"
    sheet = f"Programs Age {TARGET_AGE}"
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet)
        ws = writer.sheets[sheet]
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)
        ws.freeze_panes = "A2"
    log.info("Saved → %s", out_path)
    return out_path
