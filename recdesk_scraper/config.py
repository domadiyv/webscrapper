"""Runtime configuration. Reads from environment, with optional `.env` support."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

BASE_URL = "https://jcrec.recdesk.com/Community/Program"
FILTER_API = "https://jcrec.recdesk.com/Community/Program/FilterPrograms"

TARGET_AGE = int(os.environ.get("TARGET_AGE", "8"))
MAX_PAGES = int(os.environ.get("MAX_PAGES", "50"))

# Which registration states to report on. The portal renders a status badge only
# for non-default states, so "open" (a plain "Register Now" button, no badge) has
# to be listed explicitly or every currently-registerable program is discarded.
# Valid values: open, upcoming, waitlist, ended, offline, unknown.
REGISTRATION_STATES = frozenset(
    s.strip().lower()
    for s in os.environ.get("REGISTRATION_STATES", "open,upcoming").split(",")
    if s.strip()
)


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int
    user: str
    password: str
    to_addr: str
    from_addr: str
    use_tls: bool

    @classmethod
    def from_env(cls) -> "EmailConfig | None":
        host = os.environ.get("SMTP_HOST")
        user = os.environ.get("SMTP_USER")
        password = os.environ.get("SMTP_PASSWORD")
        to_addr = os.environ.get("EMAIL_TO")
        if not all([host, user, password, to_addr]):
            return None
        return cls(
            host=host,
            port=int(os.environ.get("SMTP_PORT", "587")),
            user=user,
            password=password,
            to_addr=to_addr,
            from_addr=os.environ.get("EMAIL_FROM", user),
            use_tls=os.environ.get("SMTP_TLS", "true").lower() == "true",
        )
