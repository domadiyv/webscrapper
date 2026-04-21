"""Gmail delivery. Sends an HTML list in the body + the Excel as an attachment."""
from __future__ import annotations

import html
import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from .config import EmailConfig, TARGET_AGE
from .exporter import date_sort_key
from .parser import COLUMNS

log = logging.getLogger(__name__)


def _sorted(programs: list[dict]) -> list[dict]:
    return sorted(programs, key=lambda p: (date_sort_key(p.get("Date(s)", "")), p.get("Program Name", "")))


def _render_text(programs: list[dict]) -> str:
    if not programs:
        return "No matching programs found today.\n"
    lines = [f"Daily RecDesk scrape — {len(programs)} programs for age {TARGET_AGE}.", ""]
    for i, p in enumerate(_sorted(programs), 1):
        lines.append(
            f"{i}. {p['Program Name']}  [{p['Category']}]\n"
            f"   Ages: {p['Age / Age Range']}  |  Dates: {p['Date(s)']}  |  "
            f"Days: {p['Day(s)']}  |  Openings: {p['Opening']} (Remaining: {p['Remaining']})"
        )
    return "\n".join(lines) + "\n"


def _render_html(programs: list[dict]) -> str:
    count = len(programs)
    if count == 0:
        return "<p>No matching programs found today.</p>"

    header_cells = "".join(
        f'<th style="text-align:left;padding:6px 10px;border-bottom:2px solid #333;'
        f'background:#f4f4f4;">{html.escape(c)}</th>'
        for c in COLUMNS
    )
    rows = []
    for p in _sorted(programs):
        cells = "".join(
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;vertical-align:top;">'
            f'{html.escape(str(p.get(c, "")))}</td>'
            for c in COLUMNS
        )
        rows.append(f"<tr>{cells}</tr>")

    return f"""\
<html>
  <body style="font-family:Arial,Helvetica,sans-serif;color:#222;">
    <h2 style="margin-bottom:4px;">RecDesk Programs — age {TARGET_AGE}</h2>
    <p style="color:#666;margin-top:0;">
      {count} matching program{'s' if count != 1 else ''} ·
      {datetime.now():%A, %B %d, %Y}
    </p>
    <table style="border-collapse:collapse;font-size:13px;">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    <p style="color:#888;font-size:12px;margin-top:16px;">
      Full spreadsheet attached.
    </p>
  </body>
</html>
"""


def send_email(out_path: Path, programs: list[dict]) -> bool:
    """Send programs as an HTML list with the Excel attached.

    Returns True if sent, False if SMTP config is incomplete.
    Raises on SMTP failure.
    """
    cfg = EmailConfig.from_env()
    if cfg is None:
        log.info("Email skipped (SMTP env vars not configured)")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"RecDesk Programs (age {TARGET_AGE}) — {datetime.now():%Y-%m-%d} ({len(programs)})"
    msg["From"] = cfg.from_addr
    msg["To"] = cfg.to_addr
    msg.set_content(_render_text(programs))
    msg.add_alternative(_render_html(programs), subtype="html")

    if out_path and out_path.exists():
        with open(out_path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=out_path.name,
            )

    with smtplib.SMTP(cfg.host, cfg.port) as smtp:
        if cfg.use_tls:
            smtp.starttls()
        smtp.login(cfg.user, cfg.password)
        smtp.send_message(msg)
    log.info("Emailed report to %s", cfg.to_addr)
    return True
