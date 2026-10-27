"""Bank statements: parsing (CAMT.052/053 XML, CSV exports of German banks),
duplicate-free import and matching with receipts and recurring costs.

Matching rules for money going out, in this order:
1. receipt: a confirmed receipt with the same total, a purchase date at
   most MATCH_DAYS before the booking (card payments are booked later) and
   no other booking yet. Taken automatically when exactly one candidate
   has a store name found in the booking text, or when there is exactly one
   candidate at all and the store is unknown; otherwise left for review.
2. fixed: exactly one recurring cost running on that day with this amount,
   or a recurring cost learned for this counterparty whose amount is within
   RECURRING_TOLERANCE (the closest one if it pays several). Before or after
   that cost's period the booking counts by itself in the cost's category.
3. counted: a category learned from earlier decisions for this counterparty.
4. counted: the category of a listed merchant (MerchantRule, e.g. the
   supermarkets as groceries) named in the counterparty.
Money coming in is counted the same way through a learned category: an
income category (salary) makes it income, a spending category makes it a
refund that lowers that category's spending. Everything else waits for
review. Every transfer to or from another of the household's own accounts
(counterparty IBAN = an account's IBAN) is ignored: it would count twice.

Credit cards: every card transaction is a booking of the card's own account
and counts like any other. The monthly debit paying the card statement is
therefore ignored: a debit on another account whose amount is the sum of the
card bookings with one statement date, booked shortly after that date.
"""

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from defusedxml import ElementTree
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from .db import BankAccount, BankTransaction, Category, CategoryRule, MerchantRule, Receipt, RecurringCost, RecurringRule, Tag, TagRule
from .stats import overlap_days, Period
from .text import normalize, normalize_store

MATCH_DAYS = 3
# a learned recurring cost takes a booking up to this far off its amount
RECURRING_TOLERANCE = 0.2
# a card statement is debited this many days before/after its date
SETTLEMENT_DAYS = (3, 14)
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
    statement_on: date | None = None


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
    ("date", ("buchungstag", "buchungsdatum", "booking date", "datum", "date", "buchung", "wertstellung", "valuta", "belegdatum")),
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
    # card statements: "Betrag" in the card's foreign currency, then "Kurs",
    # then "Betrag" in euros - take the one after the exchange rate
    rate = next((i for i, n in enumerate(names) if n in ("kurs", "wechselkurs")), None)
    if rate is not None and "amount" in mapping:
        after = next((i for i in range(rate + 1, len(names)) if names[i] == names[mapping["amount"]]), None)
        if after is not None:
            mapping["amount"] = after
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


_CARD_RE = re.compile(r"\b(\d{4})[*xX•]{4,8}(\d{4})\b")
_STATEMENT_DATE_RE = re.compile(r"abrechnungsdatum\W*(\d{1,2}\.\d{1,2}\.\d{2,4})", re.IGNORECASE)
_PAYMENT_SERVICE_RE = re.compile(r"^(?:paypal|pp|klarna|sumup|sq|zettle)\s*\*\s*", re.IGNORECASE)


def _preamble(lines: list[str], header_index: int | None) -> list[str]:
    return lines[: header_index or 0]


def card_number(lines: list[str]) -> str:
    """The masked card number above the table of a card statement, "" for
    any other statement. Only the masked form is kept."""
    for line in lines:
        found = _CARD_RE.search(line)
        if found:
            return f"{found.group(1)}********{found.group(2)}"
    return ""


def card_merchant(purpose: str) -> str:
    """Card statements have no counterparty column: the merchant is the
    purpose up to the first comma ("SOFTWARE INC, 94104 EXAMPLE.COM, CA, US"),
    without a payment service in front ("PAYPAL *SHOP" -> "SHOP"), so the
    category is learned per shop and not for PayPal."""
    merchant = purpose.split(",", 1)[0]
    merchant = _PAYMENT_SERVICE_RE.sub("", merchant.strip()) or merchant
    return " ".join(merchant.split())


def parse_csv(data: bytes) -> list[Booking]:
    """CSV exports differ per bank: preamble lines, ';' or ',', German or
    English headers, one signed amount or debit/credit columns."""
    lines, delimiter, header_index, mapping = _csv_header(data)
    if header_index is None:
        # name what was seen, so an unknown bank format can be added quickly
        first = next((line for line in lines if line.strip()), "")[:200]
        raise StatementError(f"No header with date and amount columns found (first line: {first!r})")
    preamble = _preamble(lines, header_index)
    card = bool(card_number(preamble))
    statement_on = None
    for line in preamble:
        found = _STATEMENT_DATE_RE.search(line)
        if found:
            statement_on = parse_date(found.group(1))
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
        counterparty = cell("counterparty") or (card_merchant(cell("purpose")) if card else "")
        bookings.append(
            Booking(
                booked_on,
                amount,
                counterparty[:256],
                cell("purpose")[:512],
                cell("iban").replace(" ", "")[:34],
                statement_on=statement_on if card else None,
            )
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
    for line in _preamble(lines, header_index):
        for candidate in _IBAN_RE.findall(line.upper()):
            iban = normalize_iban(candidate)
            if valid_iban(iban):
                return iban
    return ""


def statement_card(data: bytes) -> str:
    """The masked card number of a card statement, "" for other statements."""
    if _is_xml(data):
        return ""
    lines, _, header_index, _ = _csv_header(data)
    return card_number(_preamble(lines, header_index))


def own_ibans(session: Session) -> set[str]:
    return {iban for iban in session.scalars(select(BankAccount.iban)) if iban}


def statement_account(session: Session, iban: str, account_id: int | None, card: str = "") -> BankAccount | None:
    """The chosen account (it learns the IBAN or card number if it had none),
    else the one with the statement's IBAN or card number - created when it
    is new - else none."""
    if account_id is not None:
        account = session.get(BankAccount, account_id)
        if account is None:
            raise StatementError("Unknown account")
        if iban and account.iban and account.iban != iban:
            raise AccountMismatch(f"The statement belongs to the account {iban}, not to {account.name}")
        if card and (account.iban or (account.card_number and account.card_number != card)):
            raise AccountMismatch(f"The statement belongs to the card …{card[-4:]}, not to {account.name}")
        if iban and not account.iban and not account.card_number:
            account.iban = iban
        if card and not account.card_number:
            account.card_number = card
        return account
    if card:
        account = session.scalar(select(BankAccount).where(BankAccount.card_number == card))
        if account is None:
            account = BankAccount(name=f"Kreditkarte …{card[-4:]}", card_number=card)
            session.add(account)
            session.flush()
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


def has_cards(session: Session) -> bool:
    return session.scalar(select(BankAccount.id).where(BankAccount.card_number != "").limit(1)) is not None


def match(session: Session, tx: BankTransaction, own: set[str] | None = None, cards: bool = True) -> None:
    """Sets status and link of an undecided booking (see module docstring).
    cards=False skips the card statement check (no card account exists)."""
    if is_transfer(tx, own_ibans(session) if own is None else own):
        tx.status = "ignored"
        return
    card_account = card_settlement(session, tx) if cards else None
    if card_account is not None:
        tx.status, tx.settles_account_id = "ignored", card_account
        return
    if tx.amount_cents >= 0:
        apply_rule(session, tx)
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
    if apply_recurring_rule(session, tx):
        return
    apply_rule(session, tx)
    if tx.status == "review":
        apply_merchant_rule(session, tx)


def merchant_rule(session: Session, tx: BankTransaction) -> MerchantRule | None:
    """The listed merchant named in the counterparty (whole words), or in
    the purpose when the counterparty is empty; the longest keyword wins."""
    text = f" {normalize(tx.counterparty or tx.purpose)} "
    if text.isspace():
        return None
    found = [rule for rule in session.scalars(select(MerchantRule)) if f" {rule.keyword} " in text]
    return max(found, key=lambda rule: len(rule.keyword), default=None)


def apply_merchant_rule(session: Session, tx: BankTransaction) -> None:
    """Counts a payment to a listed merchant (a supermarket) in its category."""
    if tx.amount_cents >= 0:
        return
    rule = merchant_rule(session, tx)
    if rule is not None:
        tx.status, tx.category_id = "counted", rule.category_id


def apply_recurring_rule(session: Session, tx: BankTransaction) -> bool:
    """A recurring cost a person linked this counterparty to before."""
    if not tx.counterparty:
        return False
    learned = session.scalars(
        select(RecurringCost)
        .join(RecurringRule, RecurringRule.recurring_id == RecurringCost.id)
        .where(RecurringRule.pattern == counterparty_pattern(tx))
    ).all()
    amount = -tx.amount_cents
    close = [c for c in learned if abs(amount - c.amount_cents) <= RECURRING_TOLERANCE * c.amount_cents]
    if not close:
        return False
    day = Period(tx.booked_on, tx.booked_on)
    running = [c for c in close if overlap_days(c.start_on, c.end_on, day)]
    cost = min(running or close, key=lambda c: abs(amount - c.amount_cents))
    if running:
        tx.status, tx.recurring_id = "fixed", cost.id
    else:
        # the cost does not cover that day (older history): count it by itself
        tx.status, tx.category_id = "counted", cost.category_id or _other_category(session)
        tx.tags = list(cost.tags)
    return True


def _other_category(session: Session) -> int | None:
    return session.scalar(select(Category.id).where(Category.key == "other"))


def learn_recurring(session: Session, tx: BankTransaction) -> None:
    """Remembers that this counterparty pays the booking's recurring cost."""
    if not tx.counterparty or tx.recurring_id is None:
        return
    pattern = counterparty_pattern(tx)
    if session.get(RecurringRule, (pattern, tx.recurring_id)) is None:
        session.add(RecurringRule(pattern=pattern, recurring_id=tx.recurring_id))


def apply_rule(session: Session, tx: BankTransaction) -> None:
    """Counts the booking with the category (and tags) learned for its
    counterparty. An income category is never used for money going out."""
    if not tx.counterparty:
        return
    pattern = counterparty_pattern(tx)
    rule = session.scalar(select(CategoryRule).where(CategoryRule.pattern == pattern))
    if rule is None:
        return
    if tx.amount_cents < 0 and session.scalar(select(Category.kind).where(Category.id == rule.category_id)) == "income":
        return
    rule.hits += 1
    tx.status, tx.category_id = "counted", rule.category_id
    tx.tags = list(session.scalars(select(Tag).join(TagRule, TagRule.tag_id == Tag.id).where(TagRule.pattern == pattern)))


def is_transfer(tx: BankTransaction, own: set[str]) -> bool:
    """Money moved between two of the household's own accounts."""
    return bool(tx.iban) and normalize_iban(tx.iban) in own


def card_settlement(session: Session, tx: BankTransaction) -> int | None:
    """The card account whose statement this debit pays: the bookings of one
    card statement add up to exactly this amount, and the debit is booked
    around the statement date. None for card bookings themselves."""
    if tx.amount_cents >= 0 or tx.statement_on is not None:
        return None
    before, after = SETTLEMENT_DAYS
    statements = session.execute(
        select(BankTransaction.account_id, BankTransaction.statement_on, func.sum(BankTransaction.amount_cents))
        .join(BankAccount, BankAccount.id == BankTransaction.account_id)
        .where(
            BankAccount.card_number != "",
            BankTransaction.statement_on.between(tx.booked_on - timedelta(days=after), tx.booked_on + timedelta(days=before)),
        )
        .group_by(BankTransaction.account_id, BankTransaction.statement_on)
    )
    matches = [account_id for account_id, _, total in statements if total == tx.amount_cents and account_id != tx.account_id]
    return matches[0] if len(matches) == 1 else None


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
    card = statement_card(data)
    account = statement_account(session, statement_iban(data), account_id, card)
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
    # the giro debit paying this card statement may have been imported first
    settled = settle_cards(session) if card else 0
    counts = Counter(tx.status for tx in created)
    return {
        "read": len(bookings),
        "imported": len(created),
        "duplicates": len(bookings) - len(created),
        **{status: counts.get(status, 0) for status in ("receipt", "fixed", "counted", "review", "ignored")},
        "transfers": sum(is_transfer(tx, own) for tx in created),
        "settlements": settled + sum(tx.settles_account_id is not None for tx in created),
        "account_id": account.id if account else None,
        "account_name": account.name if account else None,
    }


def settle_cards(session: Session) -> int:
    """Bookings waiting for review that pay a card statement -> ignored."""
    changed = 0
    for tx in session.scalars(
        select(BankTransaction).where(
            BankTransaction.status == "review", BankTransaction.amount_cents < 0, BankTransaction.statement_on.is_(None)
        )
    ):
        card_account = card_settlement(session, tx)
        if card_account is not None:
            tx.status, tx.settles_account_id = "ignored", card_account
            changed += 1
    session.commit()
    return changed


def rematch_later(household_id: int) -> None:
    """rematch() of one household in an own session, for a background task
    after a response: saving a fixed cost should not wait for thousands of
    bookings."""
    from . import tenancy
    from .db import SessionLocal

    with SessionLocal() as session:
        tenancy.bind(session, household_id)
        rematch(session)


def _decision(tx: BankTransaction) -> tuple:
    return (tx.status, tx.receipt_id, tx.recurring_id, tx.category_id, tx.settles_account_id, tuple(t.id for t in tx.tags))


def rematch(session: Session) -> int:
    """Matches again what waits for review and what the app decided by
    itself (after new receipts, fixed costs, rules or accounts); what no
    longer fits goes back to review. A person's decisions stay. Returns the
    number of bookings whose decision changed."""
    changed = 0
    own = own_ibans(session)
    cards = has_cards(session)
    bookings = session.scalars(
        select(BankTransaction).where((BankTransaction.status == "review") | (BankTransaction.decided_by == "auto"))
    ).all()
    # flushing before every query of every booking made this slow (measured:
    # 2000 bookings 5.4 s); only a freed receipt must reach the database first
    with session.no_autoflush:
        for tx in bookings:
            before = _decision(tx)
            held_receipt = tx.receipt_id is not None
            tx.status, tx.receipt_id, tx.recurring_id, tx.category_id, tx.settles_account_id = "review", None, None, None, None
            tx.tags = []
            if held_receipt:
                session.flush()
            match(session, tx, own, cards)
            changed += _decision(tx) != before
    session.commit()
    return changed
