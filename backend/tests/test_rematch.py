"""Matching again after fixed costs change: the app's own decisions follow,
a person's decisions stay."""

import time
from datetime import date, timedelta

from test_banking import csv_rows, import_file


def d(days_ago: int) -> date:
    return date.today() - timedelta(days=days_ago)


def cats(client, auth) -> dict[str, int]:
    return {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=auth).json()}


def booking(client, auth, why: str) -> dict:
    return next(t for t in client.get("/api/v1/bank/transactions", headers=auth).json() if t["purpose"] == why)


def recurring(client, auth, cents: int) -> dict:
    body = {"name": "Verein", "category_id": cats(client, auth)["subscriptions"], "amount_cents": cents, "interval_months": 1, "start_on": d(200).isoformat()}
    return client.post("/api/v1/recurring", headers=auth, json=body).json()


def test_new_fixed_cost_takes_bookings_the_app_decided(client, auth):
    c = cats(client, auth)
    import_file(client, auth, csv_rows((d(40), "Sportverein", "Beitrag 1", "-50,00")))
    first = booking(client, auth, "Beitrag 1")
    client.patch(f"/api/v1/bank/transactions/{first['id']}", headers=auth, json={"status": "counted", "category_id": c["lifestyle"]})
    assert booking(client, auth, "Beitrag 1")["decided_by"] == "person"
    # the next one is counted by the learned category: the app's decision
    import_file(client, auth, csv_rows((d(10), "Sportverein", "Beitrag 2", "-50,00")))
    second = booking(client, auth, "Beitrag 2")
    assert second["status"] == "counted" and second["decided_by"] == "auto"

    cost = recurring(client, auth, 5000)
    # the app's booking now pays the fixed cost, the person's decision stays
    assert booking(client, auth, "Beitrag 2")["recurring_id"] == cost["id"]
    assert booking(client, auth, "Beitrag 1")["status"] == "counted"

    # the amount changes: the booking no longer fits and falls back to the category rule
    client.put(f"/api/v1/recurring/{cost['id']}", headers=auth, json={**{k: cost[k] for k in ("name", "category_id", "interval_months", "start_on")}, "amount_cents": 6000})
    assert booking(client, auth, "Beitrag 2")["status"] == "counted"
    client.put(f"/api/v1/recurring/{cost['id']}", headers=auth, json={**{k: cost[k] for k in ("name", "category_id", "interval_months", "start_on")}, "amount_cents": 5000})
    assert booking(client, auth, "Beitrag 2")["status"] == "fixed"
    # deleted: back to what the rules say
    client.delete(f"/api/v1/recurring/{cost['id']}", headers=auth)
    assert booking(client, auth, "Beitrag 2")["status"] == "counted"


def test_review_by_a_person_hands_back_to_the_app(client, auth):
    import_file(client, auth, csv_rows((d(5), "Unbekannt", "X", "-12,00")))
    tx = booking(client, auth, "X")
    client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "ignored"})
    assert booking(client, auth, "X")["decided_by"] == "person"
    client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "review"})
    assert booking(client, auth, "X")["decided_by"] == "auto"


def test_rematch_of_many_bookings_stays_fast(client, auth):
    c = cats(client, auth)
    rows = [(d(i % 300), f"Laden {i % 40}", f"Kauf {i}", f"-{10 + i % 90},{i % 100:02d}") for i in range(2000)]
    import_file(client, auth, csv_rows(*rows))
    for n in range(40):  # every shop learned: most bookings become the app's decisions
        tx = next(t for t in client.get("/api/v1/bank/transactions?status=review&limit=20000", headers=auth).json() if t["counterparty"] == f"Laden {n}")
        client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "counted", "category_id": c["groceries"]})
    started = time.perf_counter()
    client.post("/api/v1/bank/rematch", headers=auth)
    seconds = time.perf_counter() - started
    print(f"rematch of 2000 bookings: {seconds:.2f} s")
    assert seconds < 15
