"""Spending statistics over a date range.

Averages are based on calendar days. Recurring costs (instalments, yearly
bills) are spread evenly over their interval, so a yearly payment does not
spike the day it is paid. Variable and fixed costs are reported separately:
the kind of the category decides (a receipt line in "electricity" is fixed).

Income: counted incoming bank bookings in an income category. An incoming
booking counted in a spending category is a refund and lowers that
category. Bookings still waiting for review count nowhere; their sums are
reported apart, so a gap in the comparison stays visible.

One-offs: bookings a person marked as one-off (a gift, a car) count in no
category, average, balance or chart; their sums in and out are reported
apart. That covers the ones still waiting for review too.

Reset date ("ab jetzt", set by an admin): the dashboard starts there. Older
receipts, bookings and costs stay stored; no period reaches before it, and
a previous period that would is not compared.

Saved: money moved to an own savings account (and back). The giro side of
a transfer counts; a booking on the savings account counts only when the
statement of the other account is not imported (no mirror booking).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .db import BankAccount, BankTransaction, Category, Receipt, RecurringCost, Tag, get_setting

DAYS_PER_MONTH = 365.25 / 12
OTHER = "other"


@dataclass
class Period:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def overlap_days(start: date, end: date | None, period: Period) -> int:
    first = max(start, period.start)
    last = min(end or period.end, period.end)
    return max(0, (last - first).days + 1)


def recurring_daily_cents(cost: RecurringCost) -> float:
    return cost.amount_cents / (cost.interval_months * DAYS_PER_MONTH)


def first_activity(session: Session) -> date | None:
    receipt = session.scalar(select(func.min(Receipt.purchased_on)).where(Receipt.status == "confirmed"))
    recurring = session.scalar(select(func.min(RecurringCost.start_on)))
    booking = session.scalar(select(func.min(BankTransaction.booked_on)).where(BankTransaction.status == "counted"))
    candidates = [d for d in (receipt, recurring, booking) if d is not None]
    return min(candidates) if candidates else None


SINCE_KEY = "dashboard_since"


def reset_date(session: Session) -> date | None:
    value = get_setting(session, SINCE_KEY)
    return date.fromisoformat(value) if value else None


def custom_period(start: date, end: date | None, today: date | None = None) -> Period:
    """A period a person typed (end: today if left out, never in the
    future). It is not cut to the reset date (Jochen, 2026-10-27: the
    chosen period wins)."""
    today = today or date.today()
    end = min(end or today, today)
    if start > end:
        raise ValueError("start_after_end")
    return Period(start, end)


def resolve_period(session: Session, range_key: str, today: date | None = None) -> Period:
    today = today or date.today()
    if range_key == "ytd":
        start = date(today.year, 1, 1)
    elif range_key == "all":
        start = first_activity(session) or today
    else:
        days = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}.get(range_key, 30)
        start = today - timedelta(days=days - 1)
    since = reset_date(session)
    if since is not None:
        start = max(start, min(since, today))
    return Period(start, today)


def _averages(total_cents: float, days: int) -> dict:
    per_day = total_cents / days if days else 0.0
    return {
        "day": round(per_day),
        "week": round(per_day * 7),
        "month": round(per_day * DAYS_PER_MONTH),
        "year": round(per_day * 365.25),
    }


def _period_totals(session: Session, period: Period, categories: dict[int, Category]) -> dict:
    """cents per category key plus per-store and per-day sums of variable spending."""
    other_id = next((c.id for c in categories.values() if c.key == OTHER), None)
    by_category: dict[str, float] = defaultdict(float)
    # tags overlap (an entry can have several), so their sums are no shares
    by_tag: dict[int, float] = defaultdict(float)
    by_store: dict[str, list] = {}
    daily: dict[date, int] = defaultdict(int)
    receipts = session.scalars(
        select(Receipt)
        .where(Receipt.status == "confirmed", Receipt.purchased_on.between(period.start, period.end))
        .options(selectinload(Receipt.items), selectinload(Receipt.store))
    ).all()
    for receipt in receipts:
        lines = [(item.category_id or other_id, item.total_cents) for item in receipt.items]
        # what the items do not explain (rounding, unread lines) counts as other
        rest = receipt.total_cents - sum(cents for _, cents in lines)
        if rest:
            lines.append((other_id, rest))
        variable = 0
        for category_id, cents in lines:
            category = categories.get(category_id) if category_id else None
            key = category.key if category else OTHER
            by_category[key] += cents
            if category is None or category.kind == "variable":
                variable += cents
        daily[receipt.purchased_on] += variable
        name = receipt.store.name if receipt.store else "?"
        entry = by_store.setdefault(name, [0, 0])
        entry[0] += receipt.total_cents
        entry[1] += 1
    # bank bookings that count on their own (no receipt, no recurring cost):
    # spending, refunds (incoming, spending category: negative spending) and income
    by_income: dict[str, float] = defaultdict(float)
    one_off = {"in_cents": 0, "out_cents": 0, "count": 0}
    bookings = session.scalars(
        select(BankTransaction).where(
            BankTransaction.status.in_(("counted", "review")),
            BankTransaction.booked_on.between(period.start, period.end),
        )
    ).all()
    for booking in bookings:
        if booking.one_off:
            one_off["in_cents" if booking.amount_cents > 0 else "out_cents"] += abs(booking.amount_cents)
            one_off["count"] += 1
            continue
        if booking.status != "counted":
            continue
        cents = -booking.amount_cents
        category = categories.get(booking.category_id) if booking.category_id else None
        if category is not None and category.kind == "income":
            by_income[category.key] += booking.amount_cents
            continue
        by_category[category.key if category else OTHER] += cents
        for tag in booking.tags:
            by_tag[tag.id] += cents
        if category is None or category.kind == "variable":
            daily[booking.booked_on] += cents
        entry = by_store.setdefault(booking.counterparty or "?", [0, 0])
        entry[0] += cents
        entry[1] += 1
    for cost in session.scalars(select(RecurringCost)):
        days = overlap_days(cost.start_on, cost.end_on, period)
        if days:
            category = categories.get(cost.category_id) if cost.category_id else None
            cents = recurring_daily_cents(cost) * days
            by_category[category.key if category else OTHER] += cents
            for tag in cost.tags:
                by_tag[tag.id] += cents
    return {
        "by_category": by_category,
        "by_income": by_income,
        "by_tag": by_tag,
        "by_store": by_store,
        "daily": daily,
        "one_off": one_off,
        "receipt_count": len(receipts),
    }


def _open_bookings(session: Session, period: Period) -> dict:
    """Bookings waiting for review: they are neither spending nor income yet."""
    rows = session.execute(
        select(BankTransaction.amount_cents).where(
            BankTransaction.status == "review",
            BankTransaction.one_off.is_(False),
            BankTransaction.booked_on.between(period.start, period.end),
        )
    ).scalars().all()
    return {
        "count": len(rows),
        "out_cents": -sum(c for c in rows if c < 0),
        "in_cents": sum(c for c in rows if c > 0),
    }


MIRROR_DAYS = 3


def _saved(session: Session, period: Period) -> int:
    """Net cents moved to the household's savings accounts in the period."""
    accounts = session.scalars(select(BankAccount).where(BankAccount.iban != "")).all()
    own = {a.iban: a for a in accounts}
    savings = {a.id for a in accounts if a.kind == "savings" and not a.card_number}
    if not savings:
        return 0
    transfers = session.scalars(
        select(BankTransaction).where(
            BankTransaction.status == "ignored",
            # moving a one-off (a gift) to savings is no part of the balance
            BankTransaction.one_off.is_(False),
            BankTransaction.iban != "",
            BankTransaction.booked_on.between(period.start, period.end),
        )
    ).all()
    saved = 0
    mirrors: list[tuple[int, date, int]] = []
    for tx in transfers:
        other = own.get("".join(tx.iban.split()).upper())
        if other is not None and other.id in savings and tx.account_id not in savings:
            saved -= tx.amount_cents  # -100 on the giro account: 100 saved
            mirrors.append((other.id, tx.booked_on, -tx.amount_cents))
    for tx in transfers:
        other = own.get("".join(tx.iban.split()).upper())
        if tx.account_id in savings and other is not None and other.id not in savings:
            mirror = next(
                (m for m in mirrors if m[0] == tx.account_id and m[2] == tx.amount_cents and abs((m[1] - tx.booked_on).days) <= MIRROR_DAYS),
                None,
            )
            if mirror is not None:
                mirrors.remove(mirror)  # counted from the giro side already
            else:
                saved += tx.amount_cents
    return saved


def _months(period: Period) -> list[Period]:
    """The calendar months of a period, the first and last one cut to it."""
    months = []
    start = period.start
    while start <= period.end:
        following = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        months.append(Period(start, min(following - timedelta(days=1), period.end)))
        start = following
    return months


def summary(session: Session, period: Period) -> dict:
    categories = {c.id: c for c in session.scalars(select(Category))}
    by_key = {c.key: c for c in categories.values()}
    current = _period_totals(session, period, categories)

    def kind_of(key: str) -> str:
        return by_key[key].kind if key in by_key else "variable"

    # a spending category holds only spending (refunds lower it)
    variable = sum(v for k, v in current["by_category"].items() if kind_of(k) != "fixed")
    fixed = sum(v for k, v in current["by_category"].items() if kind_of(k) == "fixed")
    total = variable + fixed
    income = sum(current["by_income"].values())
    monthly = []
    for month in _months(period):
        totals = current if month == period else _period_totals(session, month, categories)
        monthly.append({
            "month": month.start.strftime("%Y-%m"),
            "income_cents": round(sum(totals["by_income"].values())),
            "spending_cents": round(sum(totals["by_category"].values())),
        })

    previous_period = Period(period.start - timedelta(days=period.days), period.start - timedelta(days=1))
    since = reset_date(session)
    previous_total = 0.0  # 0: no comparison
    if since is None or previous_period.start >= since:
        previous = _period_totals(session, previous_period, categories)
        previous_total = sum(previous["by_category"].values())

    daily = []
    day = period.start
    while day <= period.end:
        daily.append({"date": day.isoformat(), "cents": current["daily"].get(day, 0)})
        day += timedelta(days=1)

    return {
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
        "days": period.days,
        # the dashboard starts here (older data stays stored)
        "since": since.isoformat() if since else None,
        "receipt_count": current["receipt_count"],
        "total_cents": round(total),
        "variable_cents": round(variable),
        "fixed_cents": round(fixed),
        "previous_total_cents": round(previous_total),
        "income_cents": round(income),
        # what is left: saved, or still on the accounts
        "balance_cents": round(income - total),
        "savings_rate": round((income - total) / income, 4) if income > 0 else None,
        # part of the balance moved to own savings accounts
        "saved_cents": _saved(session, period),
        "open": _open_bookings(session, period),
        "one_off": current["one_off"],
        "by_income": sorted(
            (
                {
                    "key": key,
                    "name_de": by_key[key].name_de if key in by_key else key,
                    "name_en": by_key[key].name_en if key in by_key else key,
                    "color": by_key[key].color if key in by_key else "#64748b",
                    "cents": round(cents),
                }
                for key, cents in current["by_income"].items()
                if round(cents)
            ),
            key=lambda row: -row["cents"],
        ),
        "monthly": monthly,
        "average": {
            "total": _averages(total, period.days),
            "variable": _averages(variable, period.days),
            "fixed": _averages(fixed, period.days),
        },
        "by_category": sorted(
            (
                {
                    "key": key,
                    "name_de": by_key[key].name_de if key in by_key else key,
                    "name_en": by_key[key].name_en if key in by_key else key,
                    "color": by_key[key].color if key in by_key else "#64748b",
                    "kind": kind_of(key),
                    "cents": round(cents),
                }
                for key, cents in current["by_category"].items()
                if round(cents)
            ),
            key=lambda row: -row["cents"],
        ),
        "by_tag": sorted(
            (
                {"id": tag.id, "name": tag.name, "color": tag.color, "cents": round(current["by_tag"][tag.id])}
                for tag in session.scalars(select(Tag))
                if round(current["by_tag"].get(tag.id, 0))
            ),
            key=lambda row: -row["cents"],
        ),
        "by_store": sorted(
            ({"name": name, "cents": cents, "count": count} for name, (cents, count) in current["by_store"].items()),
            key=lambda row: -row["cents"],
        ),
        "daily": daily,
    }
