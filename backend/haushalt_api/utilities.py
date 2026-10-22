"""Utility meters: consumption from readings, costs from tariffs, and the
forecast of the annual settlement (credit or additional payment).

Readings are interpolated linearly between two reading dates. Outside the
first and last reading nothing is known; the forecast extrapolates the
average daily consumption of the covered days to the whole billing period.
Costs are split at tariff changes: consumption x gross unit price plus the
monthly base fee for the days of each tariff.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Meter, MeterReading, RecurringCost, Tariff, UtilityBill
from .stats import DAYS_PER_MONTH, Period, overlap_days, recurring_daily_cents


def value_at(readings: list[MeterReading], day: date) -> float | None:
    """Meter value at the start of `day`, None outside the readings."""
    if not readings or day < readings[0].read_on or day > readings[-1].read_on:
        return None
    for before, after in zip(readings, readings[1:]):
        if before.read_on <= day <= after.read_on:
            span = (after.read_on - before.read_on).days
            share = (day - before.read_on).days / span if span else 0
            return before.value + (after.value - before.value) * share
    return readings[-1].value


@dataclass
class Consumption:
    amount: float  # units consumed within the covered days
    covered: Period | None  # part of the period inside the readings

    @property
    def per_day(self) -> float | None:
        if self.covered is None or self.covered.days <= 1:
            return None
        return self.amount / (self.covered.days - 1)


def consumption(readings: list[MeterReading], period: Period) -> Consumption:
    if len(readings) < 2:
        return Consumption(0.0, None)
    start = max(period.start, readings[0].read_on)
    end = min(period.end, readings[-1].read_on)
    if end <= start:
        return Consumption(0.0, None)
    return Consumption(value_at(readings, end) - value_at(readings, start), Period(start, end))


def tariff_segments(tariffs: list[Tariff], period: Period) -> list[tuple[Tariff, Period]]:
    """Parts of the period with the tariff valid in each; days before the
    first tariff have none and are left out."""
    segments = []
    for index, tariff in enumerate(tariffs):
        until = tariffs[index + 1].valid_from - timedelta(days=1) if index + 1 < len(tariffs) else period.end
        start, end = max(tariff.valid_from, period.start), min(until, period.end)
        if start <= end:
            segments.append((tariff, Period(start, end)))
    return segments


def cost_cents(tariffs: list[Tariff], period: Period, units_per_day: float) -> float | None:
    """Gross cost of the period at an even daily consumption; None without tariff."""
    segments = tariff_segments(tariffs, period)
    if not segments:
        return None
    total = 0.0
    for tariff, part in segments:
        total += units_per_day * part.days * tariff.unit_price_ct
        total += tariff.base_fee_monthly_cents * part.days / DAYS_PER_MONTH
    return total


def billing_period(session: Session, meter: Meter, today: date | None = None) -> Period:
    """The running billing year: the day after the last bill for 12 months,
    else the calendar year."""
    today = today or date.today()
    last = session.scalar(
        select(UtilityBill.period_end)
        .where(UtilityBill.meter_id == meter.id, UtilityBill.period_end.is_not(None))
        .order_by(UtilityBill.period_end.desc())
    )
    if last is None:
        return Period(date(today.year, 1, 1), date(today.year, 12, 31))
    start = last + timedelta(days=1)
    while True:
        try:
            end = start.replace(year=start.year + 1) - timedelta(days=1)
        except ValueError:  # 29 February
            end = start.replace(year=start.year + 1, day=28)
        if end >= today or end < start:
            return Period(start, end)
        start = end + timedelta(days=1)


def paid_cents(session: Session, meter: Meter, period: Period) -> float:
    """Instalments linked to the meter, spread over the period like in the
    statistics."""
    total = 0.0
    for cost in session.scalars(select(RecurringCost).where(RecurringCost.meter_id == meter.id)):
        total += recurring_daily_cents(cost) * overlap_days(cost.start_on, cost.end_on, period)
    return total


def meter_summary(session: Session, meter: Meter, period: Period, today: date | None = None) -> dict:
    today = today or date.today()
    readings = list(meter.readings)
    used = consumption(readings, period)
    per_day = used.per_day
    projected_units = per_day * period.days if per_day is not None else None
    projected_cost = cost_cents(meter.tariffs, period, per_day) if per_day is not None else None
    paid = paid_cents(session, meter, period)
    intervals = [
        {
            "start": a.read_on.isoformat(),
            "end": b.read_on.isoformat(),
            "per_day": (b.value - a.value) / (b.read_on - a.read_on).days,
        }
        for a, b in zip(readings, readings[1:])
        if (b.read_on - a.read_on).days > 0
    ]
    return {
        "meter_id": meter.id,
        "period_start": period.start.isoformat(),
        "period_end": period.end.isoformat(),
        "covered_start": used.covered.start.isoformat() if used.covered else None,
        "covered_end": used.covered.end.isoformat() if used.covered else None,
        "consumption": round(used.amount, 3),
        "per_day": round(per_day, 4) if per_day is not None else None,
        "projected_consumption": round(projected_units, 1) if projected_units is not None else None,
        "projected_cost_cents": round(projected_cost) if projected_cost is not None else None,
        "paid_cents": round(paid),
        # positive: credit expected, negative: additional payment expected
        "projected_balance_cents": round(paid - projected_cost) if projected_cost is not None and paid else None,
        "suggested_instalment_cents": round(projected_cost / 12) if projected_cost is not None else None,
        "intervals": intervals,
        "elapsed_days": max(0, min(today, period.end).toordinal() - period.start.toordinal() + 1),
    }


def match_meter(session: Session, kind: str, meter_number: str) -> Meter | None:
    """The meter a photo or bill belongs to: same number, else the only meter
    of that kind."""
    if meter_number:
        compact = meter_number.replace(" ", "").lower()
        for meter in session.scalars(select(Meter)):
            if meter.meter_number and meter.meter_number.replace(" ", "").lower() == compact:
                return meter
    candidates = list(session.scalars(select(Meter).where(Meter.kind == kind)))
    return candidates[0] if len(candidates) == 1 else None
