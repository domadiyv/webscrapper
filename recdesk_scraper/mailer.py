"""Gmail delivery. Renders programs directly in the email body as an HTML table."""
from __future__ import annotations

import html
import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage

from .config import EmailConfig, TARGET_AGE
from .exporter import date_sort_key
from .parser import COLUMNS

log = logging.getLogger(__name__)

_LINK_COLUMN = "URL"
_DISPLAY_COLUMNS = [c for c in COLUMNS if c != _LINK_COLUMN]


def _sorted(programs: list[dict]) -> list[dict]:
    return sorted(
        programs,
        key=lambda p: (date_sort_key(p.get("Date(s)", "")), p.get("Program Name", "")),
    )


def _render_text(programs: list[dict]) -> str:
    if not programs:
        return "No matching programs found today.\n"
    lines = [f"RecDesk programs for age {TARGET_AGE} — {len(programs)} open.", ""]
    for i, p in enumerate(_sorted(programs), 1):
        lines.append(
            f"{i}. {p['Program Name']}  [{p['Category']}]\n"
            f"   Ages: {p['Age / Age Range']}  |  Dates: {p['Date(s)']}  |  "
            f"Days: {p['Day(s)']}  |  Openings: {p['Opening']} (Remaining: {p['Remaining']})\n"
            f"   {p.get('URL', '')}"
        )
    return "\n".join(lines) + "\n"


def _cell(p: dict, col: str) -> str:
    value = str(p.get(col, ""))
    if col == "Program Name":
        url = p.get("URL", "")
        if url and url != "N/A":
            return (
                f'<a href="{html.escape(url, quote=True)}" '
                f'style="color:#1a73e8;text-decoration:none;">{html.escape(value)}</a>'
            )
    return html.escape(value)


def _render_html(programs: list[dict]) -> str:
    count = len(programs)
    if count == 0:
        return (
            "<html><body style=\"font-family:Arial,sans-serif;\">"
            "<p>No matching programs found today.</p></body></html>"
        )

    header_cells = "".join(
        f'<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #333;'
        f'background:#f4f4f4;font-size:13px;">{html.escape(c)}</th>'
        for c in _DISPLAY_COLUMNS
    )
    rows = []
    for p in _sorted(programs):
        cells = "".join(
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;'
            f'vertical-align:top;font-size:13px;">{_cell(p, c)}</td>'
            for c in _DISPLAY_COLUMNS
        )
        rows.append(f"<tr>{cells}</tr>")

    return f"""\
<html>
  <body style="font-family:Arial,Helvetica,sans-serif;color:#222;">
    <h2 style="margin-bottom:4px;">RecDesk Programs — age {TARGET_AGE}</h2>
    <p style="color:#666;margin-top:0;">
      {count} open program{'s' if count != 1 else ''} ·
      {datetime.now():%A, %B %d, %Y}
    </p>
    <table style="border-collapse:collapse;">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    <p style="color:#888;font-size:12px;margin-top:16px;">
      Click a program name to open its RecDesk registration page.
    </p>
  </body>
</html>
"""


def send_email(programs: list[dict]) -> bool:
    """Send programs rendered directly in the email body.

    Returns True if sent, False if SMTP config is incomplete.
    Raises on SMTP failure.
    """
    cfg = EmailConfig.from_env()
    if cfg is None:
        log.info("Email skipped (SMTP env vars not configured)")
        return False

    msg = EmailMessage()
    msg["Subject"] = (
        f"RecDesk Programs (age {TARGET_AGE}) — "
        f"{datetime.now():%Y-%m-%d} ({len(programs)})"
    )
    msg["From"] = cfg.from_addr
    msg["To"] = cfg.to_addr
    msg.set_content(_render_text(programs))
    msg.add_alternative(_render_html(programs), subtype="html")

    with smtplib.SMTP(cfg.host, cfg.port) as smtp:
        if cfg.use_tls:
            smtp.starttls()
        smtp.login(cfg.user, cfg.password)
        smtp.send_message(msg)
    log.info("Emailed report to %s", cfg.to_addr)
    return True
