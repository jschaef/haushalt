"""Password policy after NIST SP 800-63B: length instead of composition rules.

- at least MIN_LENGTH characters (Unicode, NFKC-normalized), up to MAX_LENGTH
- no common or breached passwords, no context words (username, display name,
  app name), no runs of repeated or sequential characters
- no forced rotation; a password changes when the person wants or after a reset

data/common-passwords.txt.gz: the entries with at least 12 characters of
"100k-most-used-passwords-NCSC.txt" and "xato-net-10-million-passwords-
1000000.txt" from SecLists (github.com/danielmiessler/SecLists, MIT license),
lowercased. Shorter entries fail the length rule anyway.
"""

import gzip
import secrets
import unicodedata
from functools import cache
from pathlib import Path

MIN_LENGTH = 12
MAX_LENGTH = 128
APP_WORDS = ("haushalt", "household")

# runs that count as "sequential" (also backwards and wrapping, e.g. 789012)
_SEQUENCES = (
    "0123456789" * 3,
    "abcdefghijklmnopqrstuvwxyz" * 2,
    "qwertzuiopasdfghjklyxcvbnm" * 2,
    "qwertyuiopasdfghjklzxcvbnm" * 2,
    "azertyuiopqsdfghjklmwxcvbn" * 2,
)

# one-time passwords: no characters that are easy to confuse (0/O, 1/l/I)
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def normalize(password: str) -> str:
    return unicodedata.normalize("NFKC", password)


@cache
def _common() -> frozenset[str]:
    path = Path(__file__).parent / "data" / "common-passwords.txt.gz"
    with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as handle:
        return frozenset(line.strip() for line in handle if line.strip())


def _sequential(text: str) -> bool:
    return any(text in sequence or text[::-1] in sequence for sequence in _SEQUENCES)


def problems(password: str, *, username: str = "", display_name: str = "") -> list[str]:
    """Reasons why a password is not allowed, as codes the UI translates."""
    value = normalize(password)
    lower = value.lower()
    found = []
    if len(value) < MIN_LENGTH:
        found.append("too_short")
    if len(value) > MAX_LENGTH:
        found.append("too_long")
    if lower in _common():
        found.append("common")
    if len(set(lower)) < 4 or _sequential(lower):
        found.append("repetitive")
    words = [username, *display_name.split(), *APP_WORDS]
    if any(len(word) >= 3 and word.lower() in lower for word in words):
        found.append("personal")
    return found


def one_time_password() -> str:
    """20 random characters in groups of five, about 99 bits."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(20))
    return "-".join(raw[i : i + 5] for i in range(0, 20, 5))
