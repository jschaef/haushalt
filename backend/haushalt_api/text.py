"""Normalizing receipt texts so that the same article or store matches again."""

import re
import unicodedata

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
# weights, volumes and pack sizes vary between receipts of the same article
_PACK = re.compile(r"\b\d+\s*x\s*\d+([.,]\d+)?\s*(g|kg|ml|l|cl)?\b")
_SIZE = re.compile(r"\b\d+([.,]\d+)?\s*(g|kg|ml|l|cl|st|stk|x)\b")
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """'JA! Frischmilch 3,5% 1L' -> 'ja frischmilch 3 5'"""
    value = unicodedata.normalize("NFKC", text).lower().translate(_UMLAUTS)
    value = _PACK.sub(" ", value)
    value = _SIZE.sub(" ", value)
    value = _NON_WORD.sub(" ", value)
    return " ".join(value.split())


_STORE_SUFFIX = re.compile(r"\b(gmbh|ohg|kg|ag|co|markt|filiale|se|e k|ek)\b")


def normalize_store(name: str) -> str:
    """'REWE Markt GmbH' and 'Rewe' both become 'rewe'."""
    value = normalize(name)
    value = _STORE_SUFFIX.sub(" ", value)
    return " ".join(value.split()) or normalize(name)
