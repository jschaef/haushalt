"""Purchases: what was bought, from the lines of confirmed receipts (Jochen,
2026-10-28). Sums split into food and non-food (per category), products
grouped by their normalized text (sizes left out, case ignored), quantities
per unit, filters by period, store, category and a search text. Bank
bookings without a receipt have no articles and do not appear here.
/prices lists price changes of the same article in the same store."""

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import stats
from .auth import current_user
from .db import Category, Receipt, ReceiptItem, get_session
from .text import article_key, normalize

router = APIRouter(prefix="/api/v1/purchases", dependencies=[Depends(current_user)])

RANGE = Query(default="30d", pattern=r"^(7d|30d|90d|365d|ytd|all|custom)$")
FOOD = Query(default="all", pattern=r"^(all|food|nonfood)$")


def product_key(name: str) -> str:
    return normalize(name) or name.strip().lower()


def requested_period(session: Session, range_key: str, start: date | None, end: date | None) -> stats.Period:
    """range as on the dashboard; "custom" needs a start (end: today)."""
    if range_key != "custom":
        return stats.resolve_period(session, range_key)
    if start is None:
        raise HTTPException(status_code=422, detail="start_required")
    try:
        return stats.custom_period(start, end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _lines(
    session: Session, period: stats.Period, store_id: int | None, category_id: int | None, q: str
) -> list[tuple[ReceiptItem, Receipt]]:
    query = (
        select(ReceiptItem, Receipt)
        .join(Receipt, ReceiptItem.receipt_id == Receipt.id)
        .where(Receipt.status == "confirmed", Receipt.purchased_on.between(period.start, period.end))
        .options(selectinload(Receipt.store))
    )
    if store_id is not None:
        query = query.where(Receipt.store_id == store_id)
    if category_id is not None:
        query = query.where(ReceiptItem.category_id == category_id)
    rows = [(item, receipt) for item, receipt in session.execute(query).all()]
    needle = normalize(q) if q.strip() else ""
    if needle:
        rows = [(item, receipt) for item, receipt in rows if needle in product_key(item.name)]
    return rows


@router.get("")
def purchases(
    range: str = RANGE,
    start: date | None = None,
    end: date | None = None,
    food: str = FOOD,
    store_id: int | None = None,
    category_id: int | None = None,
    q: str = Query(default="", max_length=100),
    session: Session = Depends(get_session),
):
    """Sums for food and non-food (the food filter leaves them out, so both
    stay visible) and the products, biggest spending first."""
    period = requested_period(session, range, start, end)
    is_food = {c.id: c.is_food for c in session.scalars(select(Category))}
    sums = {"food": 0, "nonfood": 0}
    products: dict[str, dict] = {}
    for item, receipt in _lines(session, period, store_id, category_id, q):
        food_item = is_food.get(item.category_id, False)
        sums["food" if food_item else "nonfood"] += item.total_cents
        if food != "all" and (food == "food") != food_item:
            continue
        key = product_key(item.name)
        entry = products.get(key)
        if entry is None:
            entry = products[key] = {
                "key": key, "name": item.name, "category_id": item.category_id, "is_food": food_item,
                "total_cents": 0, "lines": 0, "quantities": defaultdict(float), "unit_cents": defaultdict(int),
                "stores": set(), "last_bought": receipt.purchased_on,
            }
        entry["total_cents"] += item.total_cents
        entry["lines"] += 1
        entry["quantities"][item.unit] += item.quantity
        entry["unit_cents"][item.unit] += item.total_cents
        if receipt.store is not None:
            entry["stores"].add(receipt.store.name)
        # the latest purchase names the product and decides its category
        if receipt.purchased_on >= entry["last_bought"]:
            entry.update(name=item.name, category_id=item.category_id, is_food=food_item, last_bought=receipt.purchased_on)
    out = []
    for entry in products.values():
        quantities = {unit: round(amount, 3) for unit, amount in entry["quantities"].items()}
        out.append({
            **{k: v for k, v in entry.items() if k not in ("quantities", "unit_cents", "stores")},
            "quantities": quantities,
            # average price per piece, kg or l
            "average_cents": {
                unit: round(entry["unit_cents"][unit] / amount) for unit, amount in quantities.items() if amount > 0
            },
            "stores": sorted(entry["stores"], key=str.lower),
        })
    out.sort(key=lambda p: (-p["total_cents"], p["name"].lower()))
    return {
        "start": period.start, "end": period.end,
        "food_cents": sums["food"], "nonfood_cents": sums["nonfood"], "total_cents": sums["food"] + sums["nonfood"],
        "products": out,
    }


@router.get("/lines")
def product_lines(
    key: str = Query(min_length=1, max_length=256),
    range: str = RANGE,
    start: date | None = None,
    end: date | None = None,
    store_id: int | None = None,
    session: Session = Depends(get_session),
):
    """Every purchase of one product in the period, newest first."""
    period = requested_period(session, range, start, end)
    rows = [(i, r) for i, r in _lines(session, period, store_id, None, "") if product_key(i.name) == key]
    rows.sort(key=lambda row: (row[1].purchased_on, row[1].id), reverse=True)
    return [
        {
            "receipt_id": receipt.id, "purchased_on": receipt.purchased_on,
            "store_name": receipt.store.name if receipt.store else "", "name": item.name,
            "quantity": item.quantity, "unit": item.unit, "total_cents": item.total_cents,
            "discount_cents": item.discount_cents,
        }
        for item, receipt in rows
    ]


# --- price changes (Jochen, 2026-11-16) ----------------------------------------
# The same article (text WITH pack size) in the same store, compared with its
# previous purchase. The price is the regular one before the article's discount
# (a promotion is no price drop), per piece, kg or l: the printed unit price
# where the receipt has one, else (paid + discount) / quantity.

DIRECTION = Query(default="all", pattern=r"^(all|up|down)$")
HISTORY = 24


def regular_unit_cents(item: ReceiptItem) -> tuple[float, bool] | None:
    """(price per unit before the discount, exact) - exact when printed."""
    if item.quantity <= 0 or item.total_cents + item.discount_cents <= 0:
        return None
    if item.unit_price_cents and item.unit_price_cents > 0:
        return float(item.unit_price_cents), True
    return (item.total_cents + item.discount_cents) / item.quantity, False


def _changed(old: tuple[float, float], new: tuple[float, float]) -> bool:
    """Prices as (cents, rounding error): computed prices of weighed goods carry
    the rounding of the printed total (half a cent spread over the quantity)."""
    return abs(new[0] - old[0]) > 0.5 + old[1] + new[1]


@router.get("/prices")
def price_changes(
    range: str = RANGE,
    start: date | None = None,
    end: date | None = None,
    food: str = FOOD,
    store_id: int | None = None,
    direction: str = DIRECTION,
    min_pct: float = Query(default=0, ge=0, le=1000),
    q: str = Query(default="", max_length=100),
    session: Session = Depends(get_session),
):
    """Per article and store the latest price change within the period
    (against the purchase before it, which may lie before the period),
    biggest change in percent first, with the price history."""
    period = requested_period(session, range, start, end)
    is_food = {c.id: c.is_food for c in session.scalars(select(Category))}
    query = (
        select(ReceiptItem, Receipt)
        .join(Receipt, ReceiptItem.receipt_id == Receipt.id)
        .where(Receipt.status == "confirmed", Receipt.store_id.is_not(None), Receipt.purchased_on <= period.end)
        .options(selectinload(Receipt.store))
        .order_by(Receipt.purchased_on, Receipt.id, ReceiptItem.position)
    )
    if store_id is not None:
        query = query.where(Receipt.store_id == store_id)
    needle = normalize(q) if q.strip() else ""
    series: dict[tuple, list] = defaultdict(list)
    for item, receipt in session.execute(query).all():
        price = regular_unit_cents(item)
        key = article_key(item.name)
        if price is None or not key:
            continue
        cents, exact = price
        error = 0.0 if exact or item.unit == "piece" else 0.5 / item.quantity
        series[(key, receipt.store_id, item.unit)].append((item, receipt, cents, error))
    out = []
    for (key, sid, unit), rows in series.items():
        latest_item, latest_receipt = rows[-1][0], rows[-1][1]
        if needle and needle not in normalize(latest_item.name):
            continue
        food_item = is_food.get(latest_item.category_id, False)
        if food != "all" and (food == "food") != food_item:
            continue
        change = None
        for before, after in zip(rows, rows[1:]):
            if after[1].purchased_on >= period.start and _changed(before[2:], after[2:]):
                change = (before, after)
        if change is None:
            continue
        (_, old_receipt, old, _), (_, new_receipt, new, _) = change
        old_cents, new_cents = round(old), round(new)
        pct = round((new - old) / old * 100, 1)
        if (direction == "up" and pct <= 0) or (direction == "down" and pct >= 0) or abs(pct) < min_pct:
            continue
        out.append({
            "key": key, "name": latest_item.name, "store_id": sid, "store_name": latest_receipt.store.name,
            "unit": unit, "category_id": latest_item.category_id, "is_food": food_item,
            "old_cents": old_cents, "new_cents": new_cents, "diff_cents": new_cents - old_cents, "pct": pct,
            "previous_on": old_receipt.purchased_on, "changed_on": new_receipt.purchased_on,
            "current_cents": round(rows[-1][2]), "last_bought": latest_receipt.purchased_on,
            # newest first
            "history": [
                {"date": r.purchased_on, "unit_cents": round(c), "discount_cents": i.discount_cents,
                 "quantity": i.quantity, "receipt_id": r.id}
                for i, r, c, _ in reversed(rows[-HISTORY:])
            ],
        })
    out.sort(key=lambda p: (-abs(p["pct"]), p["name"].lower()))
    return {"start": period.start, "end": period.end, "changes": out}
