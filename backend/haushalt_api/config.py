"""Settings from the environment, read once at import time.

Tests set the variables before importing the app (see tests/conftest.py).
"""

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("HAUSHALT_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATABASE_URL = os.getenv("HAUSHALT_DATABASE_URL", f"sqlite:///{DATA_DIR / 'haushalt.db'}")
RECEIPT_DIR = Path(os.getenv("HAUSHALT_RECEIPT_DIR", DATA_DIR / "receipts"))

SECRET = os.getenv("HAUSHALT_SECRET", "")
TOKEN_TTL_SECONDS = int(os.getenv("HAUSHALT_TOKEN_TTL", 30 * 24 * 3600))

# Registration is open only while no user exists, unless enabled explicitly.
# Further household members are added by a logged-in user.
ALLOW_SIGNUP = os.getenv("HAUSHALT_ALLOW_SIGNUP", "false").lower() in ("1", "true", "yes")

# "claude" reads receipts with the Anthropic API (needs ANTHROPIC_API_KEY or
# another credential the SDK finds); "fake" returns a fixed receipt for tests.
EXTRACTOR = os.getenv("HAUSHALT_EXTRACTOR", "claude")
RECEIPT_MODEL = os.getenv("HAUSHALT_RECEIPT_MODEL", "claude-opus-5-5")
RECEIPT_EFFORT = os.getenv("HAUSHALT_RECEIPT_EFFORT", "low")

MAX_UPLOAD_BYTES = int(os.getenv("HAUSHALT_MAX_UPLOAD_MB", 20)) * 1024 * 1024

API_DOCS = os.getenv("HAUSHALT_API_DOCS", "false").lower() in ("1", "true", "yes")
# failed logins per username and client address before a pause
LOGIN_MAX_FAILURES = int(os.getenv("HAUSHALT_LOGIN_MAX_FAILURES", 5))
LOGIN_BLOCK_SECONDS = int(os.getenv("HAUSHALT_LOGIN_BLOCK_SECONDS", 300))

# smart meter polling (smartmeter.py): minutes between polls, 0 = off.
# Polled addresses must be private/local unless HAUSHALT_POLL_ALLOW_PUBLIC.
POLL_MINUTES = int(os.getenv("HAUSHALT_POLL_MINUTES", 15))
POLL_ALLOW_PUBLIC = os.getenv("HAUSHALT_POLL_ALLOW_PUBLIC", "false").lower() in ("1", "true", "yes")

# Receipt photos/PDFs of confirmed receipts are deleted this many days after
# the purchase date (Jochen 2026-10-22: one year); the data read from them
# stays. 0 keeps them forever. Drafts keep their file for the review.
RECEIPT_PHOTO_DAYS = int(os.getenv("HAUSHALT_RECEIPT_PHOTO_DAYS", 365))
