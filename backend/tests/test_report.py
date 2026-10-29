"""Report (Jochen, 2026-10-29): receipt lines, bank bookings and fixed costs
as one list, filters with AND between fields, OR within a field and NOT per
field, sums and groups, CSV export. The sums follow the dashboard."""

from test_banking import csv_rows, import_file
from test_income import booking, cats, d, decide, summary
from test_one_off import mark
from test_purchases import receipt
from test_tags import tag


def report(client, auth, **params):
    response = client.get("/api/v1/report", headers=auth, params={"range": "30d", **params})
    assert response.status_code == 200, response.text
    return response.json()


def texts(data) -> set[str]:
    return {e["text"] for e in data["entries"]}


def setup(client, auth, png) -> dict:
    """Receipt with a rest, fixed cost with a tag, counted bookings with a tag,
    salary, an open booking and a one-off."""
    c = cats(client, auth)
    kid = tag(client, auth, "Kind")
    holiday = tag(client, auth, "Urlaub")
    rid = receipt(client, auth, png, "REWE", d(3), [
        ("Bio Bananen", 1.2, "kg", 239, "groceries"),
        ("Spülmittel", 1, "piece", 199, "household"),
    ])
    # the receipt says more than its lines: the rest counts as other
    client.patch(f"/api/v1/receipts/{rid}", headers=auth, json={"total_cents": 500})
    client.post("/api/v1/recurring", headers=auth, json={
        "name": "Sparplan", "category_id": c["other"], "amount_cents": 3044, "interval_months": 1,
        "start_on": d(200).isoformat(), "tag_ids": [kid]})
    import_file(client, auth, csv_rows(
        (d(5), "Arbeitgeber", "Gehalt", "2500,00"),
        (d(4), "Spielwaren Huber", "Geschenk Kind", "-25,00"),
        (d(2), "Reisebuero", "Ferien", "-400,00"),
        (d(2), "Online Shop", "Bestellung", "-30,00"),
        (d(1), "Autohaus", "Auto", "-8000,00"),
    ))
    decide(client, auth, booking(client, auth, "Arbeitgeber"), c["salary"])
    toys = booking(client, auth, "Spielwaren Huber")
    client.patch(f"/api/v1/bank/transactions/{toys['id']}", headers=auth,
                 json={"status": "counted", "category_id": c["lifestyle"], "tag_ids": [kid, holiday]})
    trip = booking(client, auth, "Reisebuero")
    client.patch(f"/api/v1/bank/transactions/{trip['id']}", headers=auth,
                 json={"status": "counted", "category_id": c["lifestyle"], "tag_ids": [holiday]})
    decide(client, auth, booking(client, auth, "Autohaus"), c["lifestyle"])
    mark(client, auth, booking(client, auth, "Autohaus"))
    # "Online Shop" stays in review: it counts nowhere
    return {"c": c, "kid": kid, "holiday": holiday, "receipt": rid}


def test_sums_follow_the_dashboard(client, auth, png):
    setup(client, auth, png)
    r = report(client, auth)
    s = summary(client, auth)
    assert r["spending_cents"] == s["total_cents"] and r["income_cents"] == s["income_cents"]
    assert r["balance_cents"] == s["balance_cents"]
    assert texts(r) >= {"Bio Bananen", "Spülmittel", "", "Sparplan", "Arbeitgeber", "Spielwaren Huber", "Reisebuero"}
    assert "Online Shop" not in texts(r) and "Autohaus" not in texts(r)
    rest = next(e for e in r["entries"] if e["rest"])
    assert rest["cents"] == 500 - 239 - 199 and rest["source"] == "receipt"
    salary = next(e for e in r["entries"] if e["text"] == "Arbeitgeber")
    assert salary["flow"] == "income" and salary["cents"] == 250000
    # one-offs only on request
    only = report(client, auth, one_off="only")
    assert texts(only) == {"Autohaus"} and only["spending_cents"] == 800000
    assert report(client, auth, one_off="include")["spending_cents"] == s["total_cents"] + 800000


def test_and_or_not(client, auth, png):
    x = setup(client, auth, png)
    c = x["c"]
    # OR within a field
    both = report(client, auth, category_id=[c["groceries"], c["household"]])
    assert texts(both) == {"Bio Bananen", "Spülmittel"} and both["spending_cents"] == 438
    # NOT: everything but lifestyle and income
    rest = report(client, auth, category_id=[c["lifestyle"], c["salary"]], category_not=True)
    assert "Reisebuero" not in texts(rest) and "Arbeitgeber" not in texts(rest) and "Bio Bananen" in texts(rest)
    # AND between fields: lifestyle with tag holiday but not tag kid
    trip = report(client, auth, category_id=[c["lifestyle"]], tag_id=[x["holiday"]])
    assert texts(trip) == {"Spielwaren Huber", "Reisebuero"}
    trip_only = report(client, auth, category_id=[c["lifestyle"]], tag_id=[x["kid"]], tag_not=True)
    assert texts(trip_only) == {"Reisebuero"}
    # source, flow, store, text, amount
    assert texts(report(client, auth, source=["fixed"])) == {"Sparplan"}
    assert texts(report(client, auth, flow="income")) == {"Arbeitgeber"}
    rewe = next(s["id"] for s in client.get("/api/v1/stores", headers=auth).json() if s["name"] == "REWE")
    assert texts(report(client, auth, store_id=[rewe])) == {"Bio Bananen", "Spülmittel", ""}
    assert rewe not in {e["store_id"] for e in report(client, auth, store_id=[rewe], store_not=True)["entries"]}
    # the text matches the purpose and the store too, without case or umlauts
    assert texts(report(client, auth, q="geschenk")) == {"Spielwaren Huber"}
    assert texts(report(client, auth, q="rewe")) == {"Bio Bananen", "Spülmittel", ""}
    assert "Spielwaren Huber" not in texts(report(client, auth, q="Geschenk", q_not=True))
    assert texts(report(client, auth, min_cents=2500, max_cents=40000, source=["bank"])) == {"Spielwaren Huber", "Reisebuero"}


def test_groups(client, auth, png):
    x = setup(client, auth, png)
    by_tag = {g["key"]: g for g in report(client, auth, group="tag", flow="spending")["groups"]}
    # tags overlap: the toy shop counts for both
    assert by_tag[x["holiday"]]["spending_cents"] == 2500 + 40000
    assert by_tag[x["kid"]]["count"] >= 2 and None in by_tag
    by_category = {g["key"]: g for g in report(client, auth, group="category")["groups"]}
    assert by_category[x["c"]["salary"]]["income_cents"] == 250000
    assert by_category[x["c"]["groceries"]]["spending_cents"] == 239
    by_store = {g["key"]: g["spending_cents"] for g in report(client, auth, group="store", source=["receipt"])["groups"]}
    assert by_store == {"REWE": 500}
    months = report(client, auth, group="month")
    assert sum(g["spending_cents"] for g in months["groups"]) in range(months["spending_cents"] - 1, months["spending_cents"] + 2)
    assert [g["key"] for g in months["groups"]] == sorted((g["key"] for g in months["groups"]), reverse=True)


def test_fixed_costs_are_one_entry_per_month(client, auth):
    client.post("/api/v1/recurring", headers=auth, json={
        "name": "Miete", "category_id": cats(client, auth)["housing"], "amount_cents": 95000, "interval_months": 1,
        "start_on": d(400).isoformat()})
    r = report(client, auth, range="90d", source=["fixed"])
    months = {e["date"][:7] for e in r["entries"]}
    assert len(r["entries"]) == len(months) >= 3
    assert all(e["until"] and e["until"][:7] == e["date"][:7] for e in r["entries"])
    assert r["spending_cents"] == summary(client, auth, "90d")["total_cents"]


def test_csv_export(client, auth, png):
    setup(client, auth, png)
    import_file(client, auth, csv_rows((d(1), "=HYPERLINK(1)", "@SUM", "-1,50")))
    decide(client, auth, booking(client, auth, "=HYPERLINK(1)"), cats(client, auth)["lifestyle"])
    response = client.get("/api/v1/report/csv", headers=auth, params={"range": "30d", "source": ["bank"]})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "auswertung.csv" in response.headers["content-disposition"]
    text = response.content.decode("utf-8")
    lines = text.lstrip("﻿").splitlines()
    assert lines[0].startswith("Datum;bis;Quelle;Text")
    trip = next(line for line in lines if "Reisebuero" in line)
    assert trip.endswith(";400,00") and "Urlaub" in trip
    # formulas are defused
    evil = next(line for line in lines if "HYPERLINK" in line)
    assert ";'=HYPERLINK(1);'@SUM;" in evil


def test_validation_and_login(client, auth):
    assert client.get("/api/v1/report", headers=auth, params={"source": ["x"]}).status_code == 422
    assert client.get("/api/v1/report", headers=auth, params={"range": "custom"}).status_code == 422
    assert client.get("/api/v1/report", headers=auth, params={"group": "x"}).status_code == 422
    assert client.get("/api/v1/report", headers=auth, params={"min_cents": -1}).status_code == 422
    assert client.get("/api/v1/report").status_code == 401
    assert client.get("/api/v1/report/csv").status_code == 401
    custom = report(client, auth, range="custom", start=d(10).isoformat(), end=d(5).isoformat())
    assert custom["start"] == d(10).isoformat() and custom["end"] == d(5).isoformat()
