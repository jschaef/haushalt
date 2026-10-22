"""Spending statistics over a date range.

Averages are based on calendar days. Recurring costs (instalments, yearly
bills) are spread evenly over their interval, so a yearly payment does not
spike the day it is paid. Variable and fixed costs are reported separately:
the kind of the category decides (a receipt line in "electricity" is fixed).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .db import BankTransaction, Category, Receipt, RecurringCost

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


def resolve_period(session: Session, range_key: str, today: date | None = None) -> Period:
    today = today or date.today()
    if range_key == "ytd":
        return Period(date(today.year, 1, 1), today)
    if range_key == "all":
        return Period(first_activity(session) or today, today)
    days = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}.get(range_key, 30)
    return Period(today - timedelta(days=days - 1), today)


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
    # bank bookings that count on their own (no receipt, no recurring cost)
    bookings = session.scalars(
        select(BankTransaction).where(
            BankTransaction.status == "counted",
            BankTransaction.amount_cents < 0,
            BankTransaction.booked_on.between(period.start, period.end),
        )
    ).all()
    for booking in bookings:
        cents = -booking.amount_cents
        category = categories.get(booking.category_id) if booking.category_id else None
        by_category[category.key if category else OTHER] += cents
        if category is None or category.kind == "variable":
            daily[booking.booked_on] += cents
        entry = by_store.setdefault(booking.counterparty or "?", [0, 0])
        entry[0] += cents
        entry[1] += 1
    for cost in session.scalars(select(RecurringCost)):
        days = overlap_days(cost.start_on, cost.end_on, period)
        if days:
            category = categories.get(cost.category_id) if cost.category_id else None
            by_category[category.key if category else OTHER] += recurring_daily_cents(cost) * days
    return {"by_category": by_category, "by_store": by_store, "daily": daily, "receipt_count": len(receipts)}


def summary(session: Session, period: Period) -> dict:
    categories = {c.id: c for c in session.scalars(select(Category))}
    by_key = {c.key: c for c in categories.values()}
    current = _period_totals(session, period, categories)

    def kind_of(key: str) -> str:
        return by_key[key].kind if key in by_key else "variable"

    variable = sum(v for k, v in current["by_category"].items() if kind_of(k) == "variable")
    fixed = sum(v for k, v in current["by_category"].items() if kind_of(k) == "fixed")
    total = variable + fixed

    previous_period = Period(period.start - timedelta(days=period.days), period.start - timedelta(days=1))
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
        "receipt_count": current["receipt_count"],
        "total_cents": round(total),
        "variable_cents": round(variable),
        "fixed_cents": round(fixed),
        "previous_total_cents": round(previous_total),
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
        "by_store": sorted(
            ({"name": name, "cents": cents, "count": count} for name, (cents, count) in current["by_store"].items()),
            key=lambda row: -row["cents"],
        ),
        "daily": daily,
    }
