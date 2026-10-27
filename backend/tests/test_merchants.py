"""Listed merchants (the supermarkets) count payments in their category,
after receipts, fixed costs and a person's own decisions."""

from test_banking import confirmed_receipt, csv_rows, import_file
from test_income import booking, cats, d, decide


def merchants(client, auth) -> dict[str, dict]:
    return {m["keyword"]: m for m in client.get("/api/v1/bank/merchants", headers=auth).json()}


def test_supermarkets_count_as_groceries(client, auth):
    c = cats(client, auth)
    listed = merchants(client, auth)
    assert {"aldi", "lidl", "netto", "edeka", "penny", "rewe", "norma"} <= listed.keys()
    assert listed["rewe"]["category_id"] == c["groceries"]
    import_file(client, auth, csv_rows(
        (d(3), "REWE Markt GmbH", "Karte 1", "-23,45"),
        (d(3), "ALDI SUED SAGT DANKE", "Karte 2", "-12,00"),
        (d(3), "Netto Marken-Discount", "Karte 3", "-5,00"),
        # a word that only contains a listed name is no match
        (d(3), "Rewerk Werkstatt", "Rechnung", "-80,00"),
        # money coming in is income or a refund: a person decides
        (d(2), "REWE Markt GmbH", "Erstattung", "3,00"),
    ))
    bookings = client.get("/api/v1/bank/transactions", headers=auth).json()
    for why in ("Karte 1", "Karte 2", "Karte 3"):
        tx = next(t for t in bookings if t["purpose"] == why)
        assert tx["status"] == "counted" and tx["category_id"] == c["groceries"] and tx["decided_by"] == "auto"
    assert booking(client, auth, "Rewerk Werkstatt")["status"] == "review"
    assert booking(client, auth, "REWE Markt GmbH", "Erstattung")["status"] == "review"


def test_person_decision_and_receipt_win(client, auth, png):
    c = cats(client, auth)
    import_file(client, auth, csv_rows((d(5), "Lidl Filiale", "Kauf 1", "-30,00")))
    decide(client, auth, booking(client, auth, "Lidl Filiale"), c["household"])
    # the person's decision is learned for this counterparty and wins
    import_file(client, auth, csv_rows((d(4), "Lidl Filiale", "Kauf 2", "-31,00")))
    assert booking(client, auth, "Lidl Filiale", "Kauf 2")["category_id"] == c["household"]
    # a confirmed receipt with this amount is taken first
    confirmed_receipt(client, auth, png, "Penny", 1999, d(2))
    import_file(client, auth, csv_rows((d(1), "PENNY Markt", "Kauf 3", "-19,99")))
    assert booking(client, auth, "PENNY Markt")["status"] == "receipt"


def test_list_is_editable_and_rematches(client, auth):
    c = cats(client, auth)
    import_file(client, auth, csv_rows((d(2), "dm-drogerie markt", "Kauf", "-9,95")))
    assert booking(client, auth, "dm-drogerie markt")["status"] == "review"
    created = client.post("/api/v1/bank/merchants", headers=auth, json={"keyword": "DM-Drogerie", "category_id": c["drugstore"]})
    assert created.status_code == 201 and created.json()["keyword"] == "dm drogerie"
    # the new entry re-matched the waiting booking
    assert booking(client, auth, "dm-drogerie markt")["category_id"] == c["drugstore"]
    assert client.post("/api/v1/bank/merchants", headers=auth, json={"keyword": "dm drogerie", "category_id": c["drugstore"]}).status_code == 409
    assert client.post("/api/v1/bank/merchants", headers=auth, json={"keyword": "!!", "category_id": c["drugstore"]}).status_code == 422
    assert client.post("/api/v1/bank/merchants", headers=auth, json={"keyword": "x", "category_id": c["salary"]}).status_code == 422
    rid = created.json()["id"]
    assert client.put(f"/api/v1/bank/merchants/{rid}", headers=auth, json={"keyword": "dm", "category_id": c["household"]}).json()["keyword"] == "dm"
    assert booking(client, auth, "dm-drogerie markt")["category_id"] == c["household"]
    # removed: the app's decision goes back to review
    assert client.delete(f"/api/v1/bank/merchants/{rid}", headers=auth).status_code == 204
    assert booking(client, auth, "dm-drogerie markt")["status"] == "review"


def test_merchants_need_login(client):
    assert client.get("/api/v1/bank/merchants").status_code == 401
