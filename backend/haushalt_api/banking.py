"""Bank statements: parsing (CAMT.052/053 XML, CSV exports of German banks),
duplicate-free import and matching with receipts and recurring costs.

Matching rules for money going out, in this order:
1. receipt: a confirmed receipt with the same total, a purchase date at
   most MATCH_DAYS before the booking (card payments are booked later) and
   no other booking yet. Taken automatically when exactly one candidate
   has a store name found in the booking text, or when there is exactly one
   candidate at all and the store is unknown; otherwise left for review.
2. fixed: exactly one recurring cost running on that day with this amount.
3. counted: a category learned from earlier decisions for this counterparty.
Everything else waits for review. Money coming in is ignored by default, and
so is every transfer to or from another of the household's own accounts
(counterparty IBAN = an account's IBAN): otherwise it would count twice.
"""

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from defusedxml import ElementTree
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from .db import BankAccount, BankTransaction, CategoryRule, Receipt, RecurringCost, Tag, TagRule
from .stats import overlap_days, Period
from .text import normalize, normalize_store

MATCH_DAYS = 3
RULE_PREFIX = "bank:"


class StatementError(ValueError):
    pass


class AccountMismatch(StatementError):
    """The statement names another IBAN than the account chosen for it."""


@dataclass
class Booking:
    booked_on: date
    amount_cents: int
    counterparty: str = ""
    purpose: str = ""
    iban: str = ""
    currency: str = "EUR"


# --- amounts and dates -------------------------------------------------------


def parse_amount(text: str) -> int:
    """'-1.234,56' / '1,234.56' / '-12,5' / '12.30 EUR' -> cents"""
    value = re.sub(r"[^\d,.\-+]", "", text.strip())
    negative = value.startswith("-") or text.strip().endswith("-")
    value = value.strip("+-")
    if not value:
        raise StatementError(f"Not an amount: {text!r}")
    if "," in value and "." in value:
        decimal = "," if value.rfind(",") > value.rfind(".") else "."
    elif "," in value:
        decimal = ","
    elif "." in value and len(value.rsplit(".", 1)[1]) != 3:
        decimal = "."
    else:
        decimal = None  # '1.234' is a thousand separator
    if decimal:
        whole, _, fraction = value.rpartition(decimal)
        whole = re.sub(r"[.,]", "", whole)
        cents = int(whole or "0") * 100 + int((fraction + "00")[:2])
    else:
        cents = int(re.sub(r"[.,]", "", value)) * 100
    return -cents if negative else cents


def parse_date(text: str) -> date:
    text = text.strip()
    for pattern in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19] if "T" in text else text, pattern).date()
        except ValueError:
            continue
    raise StatementError(f"Not a date: {text!r}")


# --- CAMT ---------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element, *path: str):
    for name in path:
        if element is None:
            return None
        element = next((c for c in element if _local(c.tag) == name), None)
    return element


def _text(element, *path: str) -> str:
    found = _child(element, *path)
    return (found.text or "").strip() if found is not None else ""


def parse_camt(data: bytes) -> list[Booking]:
    """CAMT.052/053 (any version): one booking per Ntry. defusedxml refuses
    entity expansion and external entities."""
    try:
        root = ElementTree.fromstring(data)
    except Exception as exc:  # ParseError, DefusedXmlException
        raise StatementError(f"Unreadable XML: {exc}") from exc
    bookings = []
    for entry in root.iter():
        if _local(entry.tag) != "Ntry":
            continue
        if _text(entry, "Sts", "Cd") in ("PDNG", "INFO") or _text(entry, "Sts") in ("PDNG", "INFO"):
            continue  # not booked yet
        amount_el = _child(entry, "Amt")
        if amount_el is None:
            continue
        cents = parse_amount(amount_el.text or "")
        debit = _text(entry, "CdtDbtInd") == "DBIT"
        when = _text(entry, "BookgDt", "Dt") or _text(entry, "BookgDt", "DtTm") or _text(entry, "ValDt", "Dt")
        details = _child(entry, "NtryDtls", "TxDtls")
        party_role = "Cdtr" if debit else "Dbtr"
        parties = _child(details, "RltdPties") if details is not None else None
        name = _text(parties, party_role, "Nm") or _text(parties, party_role, "Pty", "Nm") if parties is not None else ""
        iban = _text(parties, f"{party_role}Acct", "Id", "IBAN") if parties is not None else ""
        purpose_parts = []
        if details is not None:
            remittance = _child(details, "RmtInf")
            if remittance is not None:
                purpose_parts = [(u.text or "").strip() for u in remittance if _local(u.tag) == "Ustrd"]
        purpose = " ".join(p for p in purpose_parts if p) or _text(entry, "AddtlNtryInf")
        bookings.append(
            Booking(
                booked_on=parse_date(when),
                amount_cents=-cents if debit else cents,
                counterparty=name[:256],
                purpose=purpose[:512],
                iban=iban[:34],
                currency=(amount_el.get("Ccy") or "EUR")[:3],
            )
        )
    if not bookings and _local(root.tag) != "Document":
        raise StatementError("Not a CAMT document")
    return bookings


# --- CSV ----------------------------------------------------------------------

# header words (normalized) -> field; earlier entries win
COLUMNS = [
    ("date", ("buchungstag", "buchungsdatum", "booking date", "datum", "date", "buchung", "wertstellung", "valuta")),
    ("amount", ("betrag eur", "betrag", "umsatz", "amount", "betrag in eur")),
    ("debit", ("soll", "debit", "ausgang")),
    ("credit", ("haben", "credit", "eingang")),
    ("counterparty", (
        "beguenstigter zahlungspflichtiger", "beguenstigter auftraggeber", "zahlungsempfaenger in", "zahlungspflichtige r",
        "auftraggeber empfaenger", "zahlungsempfaenger",
        "empfaenger", "auftraggeber", "name", "payee", "counterparty", "gegenseite",
    )),
    ("purpose", ("verwendungszweck", "purpose", "beschreibung", "description", "buchungstext")),
    ("iban", ("iban", "kontonummer iban", "iban zahlungsbeteiligter")),
]


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise StatementError("Unknown text encoding")


def _map_header(cells: list[str]) -> dict[str, int]:
    names = [normalize(c) for c in cells]
    mapping: dict[str, int] = {}
    for field, words in COLUMNS:
        for word in words:
            # whole words only: "Datei erstellt am" is no "date", "Umsatzanzeige" no "umsatz"
            index = next(
                (i for i, n in enumerate(names) if (n == word or n.startswith(word + " ")) and i not in mapping.values()),
                None,
            )
            if index is not None:
                mapping[field] = index
                break
    return mapping


def _csv_header(data: bytes) -> tuple[list[str], str, int | None, dict[str, int]]:
    """Lines, delimiter, index and column mapping of the table header."""
    text = _decode(data)
    lines = text.splitlines()
    delimiter = ";" if text.count(";") >= text.count(",") else ","
    for index, line in enumerate(lines[:40]):
        cells = next(csv.reader([line], delimiter=delimiter), [])
        candidate = _map_header(cells) if len(cells) >= 3 else {}
        if "date" in candidate and ("amount" in candidate or "debit" in candidate):
            return lines, delimiter, index, candidate
    return lines, delimiter, None, {}


def parse_csv(data: bytes) -> list[Booking]:
    """CSV exports differ per bank: preamble lines, ';' or ',', German or
    English headers, one signed amount or debit/credit columns."""
    lines, delimiter, header_index, mapping = _csv_header(data)
    if header_index is None:
        # name what was seen, so an unknown bank format can be added quickly
        first = next((line for line in lines if line.strip()), "")[:200]
        raise StatementError(f"No header with date and amount columns found (first line: {first!r})")
    reader = csv.reader(io.StringIO("\n".join(lines[header_index + 1 :])), delimiter=delimiter)
    bookings = []
    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue

        def cell(field: str) -> str:
            index = mapping.get(field)
            return row[index].strip() if index is not None and index < len(row) else ""

        try:
            booked_on = parse_date(cell("date"))
        except StatementError:
            continue  # sums, footers
        if "amount" in mapping:
            amount = parse_amount(cell("amount"))
        else:
            debit, credit = cell("debit"), cell("credit")
            amount = -abs(parse_amount(debit)) if debit else abs(parse_amount(credit or "0"))
        bookings.append(
            Booking(booked_on, amount, cell("counterparty")[:256], cell("purpose")[:512], cell("iban").replace(" ", "")[:34])
        )
    return bookings


def _is_xml(data: bytes) -> bool:
    head = data[:200].lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    return head.startswith(b"<?xml") or head.startswith(b"<document")


def parse_statement(data: bytes) -> list[Booking]:
    return parse_camt(data) if _is_xml(data) else parse_csv(data)


# --- own accounts ------------------------------------------------------------

_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b")


def normalize_iban(text: str) -> str:
    return re.sub(r"\s", "", text or "").upper()


def valid_iban(iban: str) -> bool:
    """ISO 13616 check digits (mod 97), so a random number is no IBAN."""
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):
        return False
    digits = "".join(str(int(c, 36)) for c in iban[4:] + iban[:4])
    return int(digits) % 97 == 1


def statement_iban(data: bytes) -> str:
    """The own account a statement belongs to, "" if it does not say: the
    Acct of a CAMT statement, or an IBAN in the lines above a CSV table
    (Postbank, Sparkasse and others put the account there)."""
    if _is_xml(data):
        try:
            root = ElementTree.fromstring(data)
        except Exception:  # parse_camt reports it
            return ""
        for element in root.iter():
            if _local(element.tag) in ("Stmt", "Rpt", "Ntfctn"):
                iban = normalize_iban(_text(element, "Acct", "Id", "IBAN"))
                if valid_iban(iban):
                    return iban
        return ""
    lines, _, header_index, _ = _csv_header(data)
    for line in lines[: header_index or 0]:
        for candidate in _IBAN_RE.findall(line.upper()):
            iban = normalize_iban(candidate)
            if valid_iban(iban):
                return iban
    return ""


def own_ibans(session: Session) -> set[str]:
    return {iban for iban in session.scalars(select(BankAccount.iban)) if iban}


def statement_account(session: Session, iban: str, account_id: int | None) -> BankAccount | None:
    """The chosen account (it learns the IBAN if it had none), else the one
    with the statement's IBAN - created when it is new - else none."""
    if account_id is not None:
        account = session.get(BankAccount, account_id)
        if account is None:
            raise StatementError("Unknown account")
        if iban and account.iban and account.iban != iban:
            raise AccountMismatch(f"The statement belongs to the account {iban}, not to {account.name}")
        if iban and not account.iban:
            account.iban = iban
        return account
    if not iban:
        return None
    account = session.scalar(select(BankAccount).where(BankAccount.iban == iban))
    if account is None:
        account = BankAccount(name=f"Konto …{iban[-4:]}", iban=iban)
        session.add(account)
        session.flush()
    return account


# --- import and matching ---------------------------------------------------------


def fingerprints(bookings: list[Booking]) -> list[str]:
    """Stable ids: identical bookings in one statement are numbered, so a
    re-import of an overlapping statement adds nothing twice."""
    seen: Counter = Counter()
    result = []
    for b in bookings:
        key = f"{b.booked_on}|{b.amount_cents}|{normalize(b.counterparty)}|{normalize(b.purpose)}|{b.iban}"
        seen[key] += 1
        result.append(hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest())
    return result


def receipt_candidates(session: Session, tx: BankTransaction) -> list[Receipt]:
    taken = select(BankTransaction.receipt_id).where(BankTransaction.receipt_id.is_not(None), BankTransaction.id != tx.id)
    return list(
        session.scalars(
            select(Receipt)
            .where(
                Receipt.status == "confirmed",
                Receipt.total_cents == -tx.amount_cents,
                Receipt.purchased_on.between(tx.booked_on - timedelta(days=MATCH_DAYS), tx.booked_on + timedelta(days=1)),
                Receipt.id.not_in(taken),
            )
            .options(selectinload(Receipt.store))
        )
    )


def store_in_text(receipt: Receipt, tx: BankTransaction) -> bool:
    if receipt.store is None:
        return False
    store = normalize_store(receipt.store.name)
    haystack = f" {normalize(tx.counterparty)} {normalize(tx.purpose)} "
    return bool(store) and all(f" {word}" in haystack for word in store.split())


def match(session: Session, tx: BankTransaction, own: set[str] | None = None) -> None:
    """Sets status and link of an undecided booking (see module docstring)."""
    if is_transfer(tx, own_ibans(session) if own is None else own):
        tx.status = "ignored"
        return
    if tx.amount_cents >= 0:
        tx.status = "ignored"
        return
    candidates = receipt_candidates(session, tx)
    named = [r for r in candidates if store_in_text(r, tx)]
    if len(named) == 1 or (len(candidates) == 1 and candidates[0].store is None):
        tx.status, tx.receipt_id = "receipt", (named or candidates)[0].id
        return
    if candidates:
        return  # several or unnamed: a person decides
    day = Period(tx.booked_on, tx.booked_on)
    recurring = [
        c
        for c in session.scalars(select(RecurringCost).where(RecurringCost.amount_cents == -tx.amount_cents))
        if overlap_days(c.start_on, c.end_on, day)
    ]
    if len(recurring) == 1:
        tx.status, tx.recurring_id = "fixed", recurring[0].id
        return
    pattern = counterparty_pattern(tx)
    rule = session.scalar(select(CategoryRule).where(CategoryRule.pattern == pattern)) if tx.counterparty else None
    if rule is not None:
        rule.hits += 1
        tx.status, tx.category_id = "counted", rule.category_id
        tx.tags = list(session.scalars(select(Tag).join(TagRule, TagRule.tag_id == Tag.id).where(TagRule.pattern == pattern)))


def is_transfer(tx: BankTransaction, own: set[str]) -> bool:
    """Money moved between two of the household's own accounts."""
    return bool(tx.iban) and normalize_iban(tx.iban) in own


def counterparty_pattern(tx: BankTransaction) -> str:
    # column limit (PostgreSQL enforces it, SQLite does not)
    return (RULE_PREFIX + normalize(tx.counterparty))[:256]


def learn_counterparty(session: Session, tx: BankTransaction) -> None:
    """Remembers category and tags of a counted booking for its counterparty."""
    if not tx.counterparty or tx.category_id is None:
        return
    pattern = counterparty_pattern(tx)
    rule = session.scalar(select(CategoryRule).where(CategoryRule.pattern == pattern))
    if rule is None:
        session.add(CategoryRule(pattern=pattern, category_id=tx.category_id))
    else:
        rule.category_id = tx.category_id
    # the latest decision wins, also for the tags
    session.execute(delete(TagRule).where(TagRule.pattern == pattern))
    session.add_all(TagRule(pattern=pattern, tag_id=tag.id) for tag in tx.tags)


def import_statement(session: Session, data: bytes, account_id: int | None = None) -> dict:
    bookings = parse_statement(data)
    account = statement_account(session, statement_iban(data), account_id)
    own = own_ibans(session)
    # fingerprints stay without the account, so statements imported before
    # accounts existed are still recognised as duplicates
    prints = fingerprints(bookings)
    existing = set(session.scalars(select(BankTransaction.fingerprint).where(BankTransaction.fingerprint.in_(prints))))
    created = []
    for booking, fingerprint in zip(bookings, prints):
        if fingerprint in existing:
            continue
        tx = BankTransaction(fingerprint=fingerprint, account_id=account.id if account else None, **booking.__dict__)
        session.add(tx)
        session.flush()
        match(session, tx, own)
        created.append(tx)
    session.commit()
    counts = Counter(tx.status for tx in created)
    return {
        "read": len(bookings),
        "imported": len(created),
        "duplicates": len(bookings) - len(created),
        **{status: counts.get(status, 0) for status in ("receipt", "fixed", "counted", "review", "ignored")},
        "transfers": sum(is_transfer(tx, own) for tx in created),
        "account_id": account.id if account else None,
        "account_name": account.name if account else None,
    }


def rematch(session: Session) -> int:
    """Try again for bookings still in review, e.g. after new receipts."""
    changed = 0
    own = own_ibans(session)
    for tx in session.scalars(select(BankTransaction).where(BankTransaction.status == "review")):
        match(session, tx, own)
        changed += tx.status != "review"
    session.commit()
    return changed
