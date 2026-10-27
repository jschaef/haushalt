from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, text

from haushalt_api import db as db_module
from haushalt_api.extraction import parse_bill, parse_meter
from haushalt_api.stats import DAYS_PER_MONTH, Period
from haushalt_api.utilities import consumption, cost_cents, tariff_segments, value_at


def reading(day, value):
    return SimpleNamespace(read_on=day, value=value)


def tariff(valid_from, ct, base=0):
    return SimpleNamespace(valid_from=valid_from, unit_price_ct=ct, base_fee_monthly_cents=base)


READINGS = [reading(date(2026, 1, 1), 1000.0), reading(date(2026, 1, 11), 1100.0), reading(date(2026, 2, 10), 1400.0)]


def test_value_at_interpolates():
    assert value_at(READINGS, date(2026, 1, 1)) == 1000
    assert value_at(READINGS, date(2026, 1, 6)) == 1050
    assert value_at(READINGS, date(2026, 1, 26)) == 1250
    assert value_at(READINGS, date(2025, 12, 31)) is None
    assert value_at(READINGS, date(2026, 2, 11)) is None


def test_consumption_clamped_to_readings():
    used = consumption(READINGS, Period(date(2026, 1, 6), date(2026, 3, 31)))
    assert used.amount == 350  # 1050 -> 1400
    assert used.covered == Period(date(2026, 1, 6), date(2026, 2, 10))
    assert used.per_day == pytest.approx(350 / 35)
    assert consumption(READINGS[:1], Period(date(2026, 1, 1), date(2026, 12, 31))).covered is None


def test_tariff_segments_and_cost():
    tariffs = [tariff(date(2026, 1, 1), 30.0, 1200), tariff(date(2026, 7, 1), 40.0, 1500)]
    year = Period(date(2026, 1, 1), date(2026, 12, 31))
    segments = tariff_segments(tariffs, year)
    assert [(t.unit_price_ct, p.days) for t, p in segments] == [(30.0, 181), (40.0, 184)]
    cost = cost_cents(tariffs, year, units_per_day=10)
    expected = 10 * 181 * 30 + 1200 * 181 / DAYS_PER_MONTH + 10 * 184 * 40 + 1500 * 184 / DAYS_PER_MONTH
    assert cost == pytest.approx(expected)
    assert cost_cents([], year, 10) is None


def test_parse_meter_and_bill():
    meter = parse_meter({"is_meter": True, "kind": "gas", "value": 4711.5, "unit": "m3", "meter_number": " 12 34 "})
    assert meter == {"is_meter": True, "kind": "gas", "value": 4711.5, "unit": "m³", "meter_number": "12 34"}
    assert parse_meter({"is_meter": True, "kind": "x", "value": None, "unit": "", "meter_number": ""})["is_meter"] is False
    bill = parse_bill({"is_bill": True, "kind": "water", "total_cost": 300.5, "paid": 320, "balance": None,
                       "period_start": "2025-01-01", "period_end": "bogus", "unit": "m³"})
    assert bill["total_cents"] == 30050 and bill["balance_cents"] == 1950
    assert bill["period_start"] == date(2025, 1, 1) and bill["period_end"] is None


@pytest.fixture
def meter(client, auth):
    cats = {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=auth).json()}
    body = {"name": "Strom", "kind": "electricity", "unit": "kWh", "meter_number": "1ESY1160123456", "category_id": cats["electricity"]}
    response = client.post("/api/v1/meters", headers=auth, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_meter_crud(client, auth, meter):
    assert client.get("/api/v1/meters", headers=auth).json()[0]["name"] == "Strom"
    body = {**{k: meter[k] for k in ("name", "kind", "unit", "meter_number", "category_id")}, "name": "Hausstrom"}
    assert client.put(f"/api/v1/meters/{meter['id']}", headers=auth, json=body).json()["name"] == "Hausstrom"
    assert client.post("/api/v1/meters", headers=auth, json={**body, "kind": "nuclear"}).status_code == 422
    assert client.delete(f"/api/v1/meters/{meter['id']}", headers=auth).status_code == 204
    assert client.get("/api/v1/meters", headers=auth).json() == []


def test_readings_must_count_up(client, auth, meter):
    url = f"/api/v1/meters/{meter['id']}/readings"
    assert client.post(url, headers=auth, json={"read_on": "2026-01-01", "value": 1000}).status_code == 201
    assert client.post(url, headers=auth, json={"read_on": "2026-03-01", "value": 1500}).status_code == 201
    assert client.post(url, headers=auth, json={"read_on": "2026-02-01", "value": 900}).status_code == 422
    assert client.post(url, headers=auth, json={"read_on": "2026-02-01", "value": 1600}).status_code == 422
    assert client.post(url, headers=auth, json={"read_on": "2026-03-01", "value": 1500}).status_code == 409
    assert client.post(url, headers=auth, json={"read_on": "2026-02-01", "value": 1200}).status_code == 201
    readings = client.get(url, headers=auth).json()
    assert [r["value"] for r in readings] == [1000, 1200, 1500]
    assert client.get("/api/v1/meters", headers=auth).json()[0]["last_reading"] == {"read_on": "2026-03-01", "value": 1500}
    assert client.delete(f"/api/v1/readings/{readings[1]['id']}", headers=auth).status_code == 204


def test_summary_forecasts_settlement(client, auth, meter):
    meter_id = meter["id"]
    start = date(date.today().year, 1, 1)
    url = f"/api/v1/meters/{meter_id}/readings"
    client.post(url, headers=auth, json={"read_on": start.isoformat(), "value": 1000})
    client.post(url, headers=auth, json={"read_on": (start + timedelta(days=100)).isoformat(), "value": 1800})  # 8 kWh/day
    client.post(f"/api/v1/meters/{meter_id}/tariffs", headers=auth, json={"valid_from": start.isoformat(), "unit_price_ct": 30, "base_fee_monthly_cents": 1000})
    instalment = {"name": "Abschlag Strom", "amount_cents": 8000, "interval_months": 1, "start_on": start.isoformat(), "meter_id": meter_id}
    assert client.post("/api/v1/recurring", headers=auth, json=instalment).status_code == 201
    assert client.post("/api/v1/recurring", headers=auth, json={**instalment, "meter_id": 999}).status_code == 422

    summary = client.get(f"/api/v1/meters/{meter_id}/summary", headers=auth).json()
    days = Period(start, date(start.year, 12, 31)).days
    assert summary["period_start"] == start.isoformat()
    assert summary["consumption"] == 800 and summary["per_day"] == 8
    assert summary["projected_consumption"] == round(8 * days, 1)
    expected_cost = 8 * days * 30 + 1000 * days / DAYS_PER_MONTH
    assert summary["projected_cost_cents"] == round(expected_cost)
    paid = 8000 / DAYS_PER_MONTH * days
    assert summary["paid_cents"] == round(paid)
    assert summary["projected_balance_cents"] == round(paid - expected_cost)
    assert summary["suggested_instalment_cents"] == round(expected_cost / 12)
    assert summary["intervals"][0]["per_day"] == 8


def test_read_meter_photo_matches_meter(client, auth, meter, png):
    response = client.post("/api/v1/meters/read-photo", headers=auth, files=[("file", ("z.png", png, "image/png"))])
    assert response.status_code == 200
    assert response.json()["meter_id"] == meter["id"] and response.json()["value"] == 12345.6
    assert client.post("/api/v1/meters/read-photo", headers=auth, files=[("file", ("z.txt", b"hi", "text/plain"))]).status_code == 415


def test_bill_upload_apply_and_billing_period(client, auth, meter):
    pdf = b"%PDF-1.4 fake bill"
    bill = client.post("/api/v1/bills", headers=auth, files=[("file", ("rechnung.pdf", pdf, "application/pdf"))]).json()
    assert bill["meter_id"] == meter["id"] and bill["balance_cents"] == -6000 and bill["new_instalment_cents"] == 8500
    assert client.get(f"/api/v1/bills/{bill['id']}/file", headers=auth).content == pdf
    old = {"name": "Alt", "amount_cents": 7500, "interval_months": 1, "start_on": "2025-01-01", "meter_id": meter["id"]}
    client.post("/api/v1/recurring", headers=auth, json=old)

    applied = client.post(f"/api/v1/bills/{bill['id']}/apply", headers=auth).json()
    assert applied == {"tariff": True, "instalment": True}
    [tariff_row] = client.get(f"/api/v1/meters/{meter['id']}/tariffs", headers=auth).json()
    assert tariff_row == {"id": tariff_row["id"], "valid_from": "2025-01-01", "unit_price_ct": 32.5, "base_fee_monthly_cents": 1500}
    costs = {c["name"]: c for c in client.get("/api/v1/recurring", headers=auth).json()}
    assert costs["Alt"]["end_on"] == (date.today() - timedelta(days=1)).isoformat()
    new = next(c for name, c in costs.items() if name != "Alt")
    assert new["amount_cents"] == 8500 and new["meter_id"] == meter["id"] and new["end_on"] is None
    # applying again adds no second tariff
    assert client.post(f"/api/v1/bills/{bill['id']}/apply", headers=auth).json()["tariff"] is False

    # the running billing year starts the day after the billed period
    summary = client.get(f"/api/v1/meters/{meter['id']}/summary", headers=auth).json()
    # (bill ends 2025-12-31, so the billing years are calendar years here)
    assert summary["period_start"] == date(date.today().year, 1, 1).isoformat()
    assert client.delete(f"/api/v1/bills/{bill['id']}", headers=auth).status_code == 204


def test_bill_without_meter_cannot_be_applied(client, auth):
    bill = client.post("/api/v1/bills", headers=auth, files=[("file", ("r.pdf", b"%PDF-1.4", "application/pdf"))]).json()
    assert bill["meter_id"] is None
    assert client.post(f"/api/v1/bills/{bill['id']}/apply", headers=auth).status_code == 422


def test_utilities_need_login(client):
    assert client.get("/api/v1/meters").status_code == 401
    assert client.get("/api/v1/bills").status_code == 401


def test_migration_adds_meter_column(tmp_path, monkeypatch):
    """A database from before meters existed gets the new column."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE recurring_costs (id INTEGER PRIMARY KEY, name VARCHAR(128), category_id INTEGER, "
            "amount_cents INTEGER, interval_months INTEGER, start_on DATE, end_on DATE)"
        ))
    monkeypatch.setattr(db_module, "engine", engine)
    db_module.migrate()
    assert "meter_id" in {c["name"] for c in inspect(engine).get_columns("recurring_costs")}
