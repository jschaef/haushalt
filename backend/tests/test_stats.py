from datetime import date

import pytest

from haushalt_api.db import Category, Receipt, ReceiptItem, RecurringCost, Store, User
from haushalt_api.stats import Period, overlap_days, resolve_period, summary


def category_id(session, key):
    return next(c.id for c in session.query(Category).filter_by(key=key))


def add_receipt(session, day, items, status="confirmed", total=None, store="REWE"):
    user = session.query(User).first()
    if user is None:
        user = User(username="u", password_hash="x")
        session.add(user)
        session.flush()
    shop = session.query(Store).filter_by(normalized=store.lower()).first() or Store(name=store, normalized=store.lower())
    receipt = Receipt(user_id=user.id, store=shop, purchased_on=day, status=status)
    session.add(receipt)
    for name, cents, key in items:
        receipt.items.append(ReceiptItem(name=name, total_cents=cents, category_id=category_id(session, key)))
    receipt.total_cents = total if total is not None else sum(c for _, c, _ in items)
    session.commit()
    return receipt


def test_overlap_days():
    period = Period(date(2026, 10, 1), date(2026, 10, 31))
    assert overlap_days(date(2026, 1, 1), None, period) == 31
    assert overlap_days(date(2026, 10, 25), None, period) == 7
    assert overlap_days(date(2026, 1, 1), date(2026, 10, 2), period) == 2
    assert overlap_days(date(2026, 11, 1), None, period) == 0


def test_resolve_period(session):
    today = date(2026, 10, 22)
    assert resolve_period(session, "7d", today) == Period(date(2026, 10, 16), today)
    assert resolve_period(session, "ytd", today) == Period(date(2026, 1, 1), today)
    assert resolve_period(session, "bogus", today).days == 30


def test_averages_variable_only(session):
    add_receipt(session, date(2026, 10, 1), [("Milch", 1000, "groceries"), ("Wein", 500, "drinks")])
    add_receipt(session, date(2026, 10, 10), [("Shampoo", 1500, "drugstore")])
    add_receipt(session, date(2026, 10, 11), [("Draft", 99999, "groceries")], status="draft")
    add_receipt(session, date(2026, 9, 30), [("Vorher", 3000, "groceries")])
    result = summary(session, Period(date(2026, 10, 1), date(2026, 10, 30)))
    assert result["days"] == 30
    assert result["receipt_count"] == 2
    assert result["variable_cents"] == 3000 and result["fixed_cents"] == 0
    assert result["average"]["total"]["day"] == 100
    assert result["average"]["total"]["week"] == 700
    assert result["average"]["total"]["year"] == 36525
    assert result["average"]["total"]["month"] == round(100 * 365.25 / 12)
    assert result["previous_total_cents"] == 3000
    by_category = {c["key"]: c["cents"] for c in result["by_category"]}
    assert by_category == {"groceries": 1000, "drinks": 500, "drugstore": 1500}
    assert result["by_category"][0]["key"] == "drugstore"
    assert result["by_store"] == [{"name": "REWE", "cents": 3000, "count": 2}]
    assert len(result["daily"]) == 30
    assert result["daily"][0] == {"date": "2026-10-01", "cents": 1500}


def test_unexplained_rest_counts_as_other(session):
    add_receipt(session, date(2026, 10, 1), [("Milch", 1000, "groceries")], total=1250)
    result = summary(session, Period(date(2026, 10, 1), date(2026, 10, 1)))
    assert {c["key"]: c["cents"] for c in result["by_category"]} == {"groceries": 1000, "other": 250}
    assert result["total_cents"] == 1250


def test_recurring_costs_are_spread(session):
    # yearly water bill of 365.25 EUR -> 1 EUR per day, whenever it is paid
    session.add(RecurringCost(name="Wasser", category_id=category_id(session, "water"), amount_cents=36525,
                              interval_months=12, start_on=date(2026, 1, 1)))
    # monthly electricity instalment, ended in the middle of the period
    session.add(RecurringCost(name="Strom", category_id=category_id(session, "electricity"), amount_cents=6000,
                              interval_months=1, start_on=date(2026, 1, 1), end_on=date(2026, 10, 10)))
    session.commit()
    add_receipt(session, date(2026, 10, 5), [("Einkauf", 2000, "groceries")])
    result = summary(session, Period(date(2026, 10, 1), date(2026, 10, 20)))
    electricity = round(6000 / (365.25 / 12) * 10)
    assert result["fixed_cents"] == 2000 + electricity
    assert result["variable_cents"] == 2000
    assert result["average"]["fixed"]["day"] == round((2000 + electricity) / 20)
    assert result["average"]["variable"]["day"] == 100
    # recurring costs do not appear in the daily series of variable spending
    assert sum(d["cents"] for d in result["daily"]) == 2000


def test_receipt_line_in_fixed_category_is_fixed(session):
    add_receipt(session, date(2026, 10, 1), [("Abschlag Strom", 8000, "electricity"), ("Brot", 300, "groceries")])
    result = summary(session, Period(date(2026, 10, 1), date(2026, 10, 1)))
    assert result["fixed_cents"] == 8000 and result["variable_cents"] == 300
    assert result["daily"][0]["cents"] == 300


def test_empty_database(session):
    result = summary(session, resolve_period(session, "all", date(2026, 10, 22)))
    assert result["days"] == 1 and result["total_cents"] == 0 and result["by_category"] == []


def test_stats_endpoint(client, auth):
    response = client.get("/api/v1/stats/summary?range=90d", headers=auth)
    assert response.status_code == 200 and response.json()["days"] == 90
    assert client.get("/api/v1/stats/summary?range=1y", headers=auth).status_code == 422


def test_recurring_endpoints(client, auth):
    water = next(c["id"] for c in client.get("/api/v1/categories", headers=auth).json() if c["key"] == "water")
    body = {"name": "Wasser", "category_id": water, "amount_cents": 36525, "interval_months": 12, "start_on": "2026-01-01"}
    created = client.post("/api/v1/recurring", headers=auth, json=body)
    assert created.status_code == 201 and created.json()["daily_cents"] == 100
    cost_id = created.json()["id"]
    body["amount_cents"] = 73050
    assert client.put(f"/api/v1/recurring/{cost_id}", headers=auth, json=body).json()["daily_cents"] == 200
    assert client.post("/api/v1/recurring", headers=auth, json={**body, "amount_cents": 0}).status_code == 422
    assert client.post("/api/v1/recurring", headers=auth, json={**body, "category_id": 999}).status_code == 422
    assert client.delete(f"/api/v1/recurring/{cost_id}", headers=auth).status_code == 204
    assert client.get("/api/v1/recurring", headers=auth).json() == []
