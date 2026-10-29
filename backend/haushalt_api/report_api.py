"""Report ("Auswertung", Jochen, 2026-10-29): receipt lines, bank bookings
and fixed costs as one list of entries, filtered, summed and grouped.

The entries follow the counting rules of the dashboard (stats.py): lines of
confirmed receipts (what the lines do not explain counts as "other"),
bookings counted by themselves, recurring costs spread over their interval
(one entry per cost and calendar month of the period). One-offs stay out
unless asked for. Spending is positive, a refund lowers it; income is its
own flow.

Filters (Jochen: "UND/ODER/NICHT reicht"): different fields are combined
with AND, several values of one field with OR, and every field can be
negated (NOT). No nested conditions."""

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import stats
from .auth import current_user
from .purchases_api import requested_period
from .db import BankAccount, BankTransaction, Category, Receipt, RecurringCost, Tag, User, get_session
from .text import normalize

router = APIRouter(prefix="/api/v1/report", dependencies=[Depends(current_user)])

SOURCES = ("receipt", "bank", "fixed")
GROUPS = ("none", "month", "category", "tag", "store", "source", "account")
# the page shows the newest entries; the CSV export (GET /csv) carries all of them
MAX_ENTRIES = 500


@dataclass
class Entry:
    source: str
    on: date
    cents: float
    flow: str = "spending"  # or "income"
    text: str = ""
    detail: str = ""
    category_id: int | None = None
    tag_ids: list[int] = field(default_factory=list)
    store_id: int | None = None
    account_id: int | None = None
    one_off: bool = False
    # fixed costs: the end of the month slice
    until: date | None = None
    receipt_id: int | None = None
    transaction_id: int | None = None
    recurring_id: int | None = None
    # receipt: the part of the total its lines do not explain
    rest: bool = False

    @property
    def merchant(self) -> str:
        return self.detail if self.source == "receipt" else self.text

    def out(self) -> dict:
        return {
            "source": self.source,
            "date": self.on.isoformat(),
            "until": self.until.isoformat() if self.until else None,
            "cents": round(self.cents),
            "flow": self.flow,
            "text": self.text,
            "detail": self.detail,
            "category_id": self.category_id,
            "tag_ids": self.tag_ids,
            "store_id": self.store_id,
            "account_id": self.account_id,
            "one_off": self.one_off,
            "receipt_id": self.receipt_id,
            "transaction_id": self.transaction_id,
            "recurring_id": self.recurring_id,
            "rest": self.rest,
        }


@dataclass
class Filter:
    """One field: values combined with OR; negate = NOT. Empty = no condition."""

    values: list
    negate: bool = False

    def passes(self, have: set) -> bool:
        if not self.values:
            return True
        return bool(have & set(self.values)) != self.negate


def _entries(session: Session, period: stats.Period, one_off: str) -> list[Entry]:
    categories = {c.id: c for c in session.scalars(select(Category))}
    other_id = next((c.id for c in categories.values() if c.key == stats.OTHER), None)
    entries: list[Entry] = []
    if one_off != "only":
        receipts = session.scalars(
            select(Receipt)
            .where(Receipt.status == "confirmed", Receipt.purchased_on.between(period.start, period.end))
            .options(selectinload(Receipt.items), selectinload(Receipt.store))
        ).all()
        for receipt in receipts:
            store = receipt.store.name if receipt.store else ""
            common = {"source": "receipt", "on": receipt.purchased_on, "detail": store, "store_id": receipt.store_id, "receipt_id": receipt.id}
            for item in receipt.items:
                entries.append(Entry(cents=item.total_cents, text=item.name, category_id=item.category_id or other_id, **common))
            rest = receipt.total_cents - sum(item.total_cents for item in receipt.items)
            if rest:
                entries.append(Entry(cents=rest, category_id=other_id, rest=True, **common))
        for cost in session.scalars(select(RecurringCost)):
            daily = stats.recurring_daily_cents(cost)
            for month in stats._months(period):
                days = stats.overlap_days(cost.start_on, cost.end_on, month)
                if not days:
                    continue
                entries.append(Entry(
                    source="fixed", on=max(cost.start_on, month.start), until=min(cost.end_on or month.end, month.end),
                    cents=daily * days, text=cost.name, category_id=cost.category_id or other_id,
                    tag_ids=[t.id for t in cost.tags], recurring_id=cost.id,
                ))
    # counted bookings; one-offs also while they wait for review (as on the dashboard)
    bookings = session.scalars(
        select(BankTransaction).where(
            BankTransaction.status.in_(("counted", "review")),
            BankTransaction.booked_on.between(period.start, period.end),
        )
    ).all()
    for booking in bookings:
        if (one_off == "exclude" and booking.one_off) or (one_off == "only" and not booking.one_off):
            continue
        if not booking.one_off and booking.status != "counted":
            continue
        category = categories.get(booking.category_id) if booking.status == "counted" and booking.category_id else None
        income = category.kind == "income" if category else booking.status == "review" and booking.amount_cents > 0
        entries.append(Entry(
            source="bank", on=booking.booked_on,
            cents=booking.amount_cents if income else -booking.amount_cents,
            flow="income" if income else "spending",
            text=booking.counterparty, detail=booking.purpose,
            category_id=category.id if category else (other_id if booking.status == "counted" else None),
            tag_ids=[t.id for t in booking.tags], account_id=booking.account_id,
            one_off=booking.one_off, transaction_id=booking.id,
        ))
    return entries


@dataclass
class Params:
    range: str = Query(default="30d", pattern=r"^(7d|30d|90d|365d|ytd|all|custom)$")
    start: date | None = None
    end: date | None = None
    flow: str = Query(default="all", pattern=r"^(all|spending|income)$")
    one_off: str = Query(default="exclude", pattern=r"^(exclude|include|only)$")
    source: list[str] = Query(default=[])
    category_id: list[int] = Query(default=[])
    category_not: bool = False
    tag_id: list[int] = Query(default=[])
    tag_not: bool = False
    store_id: list[int] = Query(default=[])
    store_not: bool = False
    account_id: list[int] = Query(default=[])
    account_not: bool = False
    q: str = Query(default="", max_length=100)
    q_not: bool = False
    # euros as cents, compared with the amount without sign
    min_cents: int | None = Query(default=None, ge=0)
    max_cents: int | None = Query(default=None, ge=0)


def _selected(session: Session, p: Params) -> tuple[stats.Period, list[Entry]]:
    if any(s not in SOURCES for s in p.source):
        raise HTTPException(status_code=422, detail="unknown_source")
    period = requested_period(session, p.range, p.start, p.end)
    needle = normalize(p.q) if p.q.strip() else ""
    checks = [
        (Filter(p.source), lambda e: {e.source}),
        (Filter(p.category_id, p.category_not), lambda e: {e.category_id}),
        (Filter(p.tag_id, p.tag_not), lambda e: set(e.tag_ids)),
        (Filter(p.store_id, p.store_not), lambda e: {e.store_id}),
        (Filter(p.account_id, p.account_not), lambda e: {e.account_id}),
    ]
    selected = []
    for entry in _entries(session, period, p.one_off):
        if p.flow != "all" and entry.flow != p.flow:
            continue
        if not all(f.passes(have(entry)) for f, have in checks):
            continue
        if needle and (needle in normalize(f"{entry.text} {entry.detail}")) == p.q_not:
            continue
        size = abs(entry.cents)
        if (p.min_cents is not None and size < p.min_cents) or (p.max_cents is not None and size > p.max_cents):
            continue
        selected.append(entry)
    selected.sort(key=lambda e: (e.on, e.source, e.text.lower()), reverse=True)
    return period, selected


def _group_keys(entry: Entry, group: str) -> list:
    if group == "month":
        return [entry.on.strftime("%Y-%m")]
    if group == "category":
        return [entry.category_id]
    if group == "tag":
        # tags overlap: an entry with two tags counts in both groups
        return entry.tag_ids or [None]
    if group == "store":
        return [entry.merchant or None]
    if group == "account":
        return [entry.account_id]
    return [entry.source]


@router.get("")
def report(p: Params = Depends(), group: str = Query(default="none", pattern="^(" + "|".join(GROUPS) + ")$"),
           session: Session = Depends(get_session)):
    period, selected = _selected(session, p)
    spending = sum(e.cents for e in selected if e.flow == "spending")
    income = sum(e.cents for e in selected if e.flow == "income")
    groups: dict = defaultdict(lambda: {"spending": 0.0, "income": 0.0, "count": 0})
    if group != "none":
        for entry in selected:
            for key in _group_keys(entry, group):
                g = groups[key]
                g[entry.flow] += entry.cents
                g["count"] += 1
    rows = [
        {"key": key, "spending_cents": round(g["spending"]), "income_cents": round(g["income"]), "count": g["count"]}
        for key, g in groups.items()
    ]
    if group == "month":
        rows.sort(key=lambda r: r["key"], reverse=True)
    else:
        rows.sort(key=lambda r: (-(r["spending_cents"] + r["income_cents"]), str(r["key"])))
    return {
        "start": period.start, "end": period.end,
        "spending_cents": round(spending), "income_cents": round(income), "balance_cents": round(income - spending),
        "count": len(selected),
        "groups": rows,
        "entries": [e.out() for e in selected[:MAX_ENTRIES]],
        "truncated": len(selected) > MAX_ENTRIES,
    }


def _cell(value: str) -> str:
    # a spreadsheet would run text starting with these as a formula
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@router.get("/csv")
def export(p: Params = Depends(), user: User = Depends(current_user), session: Session = Depends(get_session)):
    """All selected entries, semicolon separated with decimal commas (German
    spreadsheets), UTF-8 with BOM."""
    _, selected = _selected(session, p)
    de = user.locale == "de"
    categories = {c.id: (c.name_de if de else c.name_en) for c in session.scalars(select(Category))}
    tags = {t.id: t.name for t in session.scalars(select(Tag))}
    accounts = {a.id: a.name for a in session.scalars(select(BankAccount))}
    sources = {"receipt": "Beleg", "bank": "Bank", "fixed": "Fixkosten"} if de else {"receipt": "Receipt", "bank": "Bank", "fixed": "Fixed cost"}
    flows = {"spending": "Ausgabe", "income": "Einnahme"} if de else {"spending": "Spending", "income": "Income"}
    head = (["Datum", "bis", "Quelle", "Text", "Detail", "Kategorie", "Schlagwörter", "Konto", "Art", "Einmalig", "Betrag"] if de
            else ["Date", "Until", "Source", "Text", "Detail", "Category", "Tags", "Account", "Flow", "One-off", "Amount"])
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";" if de else ",", lineterminator="\r\n")
    writer.writerow(head)
    for e in selected:
        amount = f"{round(e.cents) / 100:.2f}"
        writer.writerow([
            e.on.isoformat(), e.until.isoformat() if e.until else "", sources[e.source],
            _cell(e.text), _cell(e.detail), _cell(categories.get(e.category_id, "")),
            _cell(", ".join(tags[t] for t in e.tag_ids if t in tags)), _cell(accounts.get(e.account_id, "")),
            flows[e.flow], ("ja" if de else "yes") if e.one_off else "", amount.replace(".", ",") if de else amount,
        ])
    return Response(
        "﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": 'attachment; filename="auswertung.csv"' if de else 'attachment; filename="report.csv"',
                 "cache-control": "no-store"},
    )
