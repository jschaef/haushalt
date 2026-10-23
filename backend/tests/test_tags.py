"""Tags next to the category: bank bookings and recurring costs, learned per
counterparty, own sums in the statistics."""

from datetime import date, timedelta

from test_banking import csv_rows, import_file
from test_utilities import meter  # noqa: F401 - fixture


def d(days_ago: int) -> date:
    return date.today() - timedelta(days=days_ago)


def tag(client, auth, name: str, color: str = "#0033a0") -> int:
    response = client.post("/api/v1/tags", headers=auth, json={"name": name, "color": color})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def cats(client, auth) -> dict[str, int]:
    return {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=auth).json()}


def test_tag_crud_and_unique_names(client, auth):
    child = tag(client, auth, "  Kind   eins ")
    assert client.get("/api/v1/tags", headers=auth).json() == [{"id": child, "name": "Kind eins", "color": "#0033a0"}]
    assert client.post("/api/v1/tags", headers=auth, json={"name": "kind EINS"}).status_code == 409
    assert client.post("/api/v1/tags", headers=auth, json={"name": "   "}).status_code == 422
    assert client.post("/api/v1/tags", headers=auth, json={"name": "x", "color": "red"}).status_code == 422
    holiday = tag(client, auth, "Urlaub")
    assert client.put(f"/api/v1/tags/{holiday}", headers=auth, json={"name": "Kind eins"}).status_code == 409
    renamed = client.put(f"/api/v1/tags/{holiday}", headers=auth, json={"name": "Urlaub 2026", "color": "#005c66"})
    assert renamed.json() == {"id": holiday, "name": "Urlaub 2026", "color": "#005c66"}
    assert client.delete(f"/api/v1/tags/{holiday}", headers=auth).status_code == 204
    assert client.delete(f"/api/v1/tags/{holiday}", headers=auth).status_code == 404
    assert client.get("/api/v1/tags").status_code == 401


def test_recurring_cost_tags_and_sums(client, auth):
    child, savings = tag(client, auth, "Kind"), tag(client, auth, "Urlaub")
    body = {"name": "Sparplan", "category_id": cats(client, auth)["other"], "amount_cents": 3044, "interval_months": 1,
            "start_on": d(200).isoformat(), "tag_ids": [child, savings, child]}
    created = client.post("/api/v1/recurring", headers=auth, json=body)
    assert created.status_code == 201
    assert sorted(created.json()["tag_ids"]) == sorted([child, savings])
    assert client.post("/api/v1/recurring", headers=auth, json={**body, "tag_ids": [999]}).status_code == 422

    summary = client.get("/api/v1/stats/summary?range=30d", headers=auth).json()
    sums = {row["name"]: row["cents"] for row in summary["by_tag"]}
    # 30 days of a monthly 30.44 EUR, counted for each tag; categories unchanged
    assert sums == {"Kind": 3000, "Urlaub": 3000}
    assert summary["total_cents"] == 3000

    cost_id = created.json()["id"]
    updated = client.put(f"/api/v1/recurring/{cost_id}", headers=auth, json={**body, "tag_ids": [savings]})
    assert updated.json()["tag_ids"] == [savings]
    # an update without tag_ids (e.g. from the utilities page) keeps them
    without = {k: v for k, v in body.items() if k != "tag_ids"}
    assert client.put(f"/api/v1/recurring/{cost_id}", headers=auth, json=without).json()["tag_ids"] == [savings]
    # deleting a tag removes it from the cost
    client.delete(f"/api/v1/tags/{savings}", headers=auth)
    [cost] = client.get("/api/v1/recurring", headers=auth).json()
    assert cost["tag_ids"] == []


def test_counted_booking_tags_are_learned_for_the_counterparty(client, auth):
    child, gifts = tag(client, auth, "Kind"), cats(client, auth)["lifestyle"]
    import_file(client, auth, csv_rows((d(3), "Spielwaren Huber", "Geschenk", "-25,00")))
    [tx] = client.get("/api/v1/bank/transactions?status=review", headers=auth).json()
    decided = client.patch(
        f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "counted", "category_id": gifts, "tag_ids": [child]}
    ).json()
    assert decided["tag_ids"] == [child]

    # the next booking from the same counterparty gets category and tags
    result = import_file(client, auth, csv_rows((d(1), "SPIELWAREN HUBER", "Geschenk 2", "-15,00"))).json()
    assert result["counted"] == 1
    txs = [t for t in client.get("/api/v1/bank/transactions?status=counted", headers=auth).json()]
    assert all(t["tag_ids"] == [child] and t["category_id"] == gifts for t in txs) and len(txs) == 2

    summary = client.get("/api/v1/stats/summary?range=7d", headers=auth).json()
    assert {"id": child, "name": "Kind", "color": "#0033a0", "cents": 4000} in summary["by_tag"]

    # another decision for the counterparty replaces the learned tags
    client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "counted", "category_id": gifts, "tag_ids": []})
    import_file(client, auth, csv_rows((d(0), "Spielwaren Huber", "Geschenk 3", "-5,00")))
    newest = client.get("/api/v1/bank/transactions?status=counted", headers=auth).json()[0]
    assert newest["purpose"] == "Geschenk 3" and newest["tag_ids"] == []


def test_tags_only_stay_on_counted_bookings(client, auth):
    child = tag(client, auth, "Kind")
    import_file(client, auth, csv_rows((d(2), "Laden", "Kauf", "-9,00")))
    [tx] = client.get("/api/v1/bank/transactions?status=review", headers=auth).json()
    url = f"/api/v1/bank/transactions/{tx['id']}"
    client.patch(url, headers=auth, json={"status": "counted", "category_id": cats(client, auth)["other"], "tag_ids": [child]})
    # ignoring drops the tags: an ignored booking counts nowhere
    assert client.patch(url, headers=auth, json={"status": "ignored", "tag_ids": [child]}).json()["tag_ids"] == []
    assert client.patch(url, headers=auth, json={"status": "counted", "category_id": 1, "tag_ids": [404]}).status_code == 422
    assert client.get("/api/v1/stats/summary?range=7d", headers=auth).json()["by_tag"] == []


def test_new_instalment_from_a_bill_keeps_the_tags(client, auth, meter):
    home = tag(client, auth, "Wohnung")
    old = {"name": "Alt", "amount_cents": 7500, "interval_months": 1, "start_on": "2025-01-01", "meter_id": meter["id"], "tag_ids": [home]}
    client.post("/api/v1/recurring", headers=auth, json=old)
    bill = client.post("/api/v1/bills", headers=auth, files=[("file", ("r.pdf", b"%PDF-1.4 fake bill", "application/pdf"))]).json()
    assert client.post(f"/api/v1/bills/{bill['id']}/apply", headers=auth).json()["instalment"] is True
    new = next(c for c in client.get("/api/v1/recurring", headers=auth).json() if c["name"] != "Alt")
    assert new["tag_ids"] == [home]
