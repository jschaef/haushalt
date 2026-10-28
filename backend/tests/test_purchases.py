"""Purchases overview (Jochen, 2026-10-28): what was bought, from confirmed
receipts - food and non-food per category, products grouped by their text,
quantities per unit, filters by period, store, category and search."""

from datetime import date, timedelta

from test_receipts import upload

TODAY = date.today()


def cats(client, auth) -> dict[str, dict]:
    return {c["key"]: c for c in client.get("/api/v1/categories", headers=auth).json()}


def receipt(client, auth, png, store, day, items, confirm=True):
    """items: (name, quantity, unit, total_cents, category_key)"""
    c = cats(client, auth)
    [r] = upload(client, auth, png + store.encode() + day.isoformat().encode()).json()
    lines = [{"name": n, "quantity": q, "unit": u, "total_cents": t, "category_id": c[k]["id"]} for n, q, u, t, k in items]
    patched = client.patch(f"/api/v1/receipts/{r['id']}", headers=auth, json={
        "store_name": store, "purchased_on": day.isoformat(), "total_cents": sum(i[3] for i in items), "items": lines})
    assert patched.status_code == 200, patched.text
    if confirm:
        assert client.post(f"/api/v1/receipts/{r['id']}/confirm", headers=auth).status_code == 200
    return r["id"]


def purchases(client, auth, **params):
    response = client.get("/api/v1/purchases", headers=auth, params={"range": "30d", **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_categories_say_what_is_food(client, auth):
    c = cats(client, auth)
    assert c["groceries"]["is_food"] and c["drinks"]["is_food"]
    assert not c["drugstore"]["is_food"] and not c["deposit"]["is_food"]
    # switch it on for a category; an update without the field keeps it
    drug = c["drugstore"]
    body = {k: drug[k] for k in ("key", "name_de", "name_en", "kind", "color", "icon")}
    assert client.put(f"/api/v1/categories/{drug['id']}", headers=auth, json={**body, "is_food": True}).json()["is_food"]
    assert client.put(f"/api/v1/categories/{drug['id']}", headers=auth, json=body).json()["is_food"]
    new = client.post("/api/v1/categories", headers=auth, json={"key": "pets", "name_de": "Tier", "name_en": "Pets"}).json()
    assert new["is_food"] is False


def test_products_sums_quantities_and_filters(client, auth, png):
    receipt(client, auth, png, "LIDL", TODAY - timedelta(days=2), [
        ("Bio Bananen", 1.2, "kg", 239, "groceries"),
        ("JA! Milch 1L", 2, "piece", 218, "groceries"),
        ("Spülmittel", 1, "piece", 199, "household"),
    ])
    receipt(client, auth, png, "REWE", TODAY - timedelta(days=1), [
        ("BIO BANANEN", 0.8, "kg", 159, "groceries"),
        ("Mineralwasser 6x1,5L", 1, "piece", 354, "drinks"),
    ])
    # drafts and purchases outside the period do not count
    receipt(client, auth, png, "LIDL", TODAY, [("Bio Bananen", 5, "kg", 999, "groceries")], confirm=False)
    receipt(client, auth, png, "LIDL", TODAY - timedelta(days=60), [("Bio Bananen", 5, "kg", 999, "groceries")])

    p = purchases(client, auth)
    assert (p["food_cents"], p["nonfood_cents"], p["total_cents"]) == (239 + 218 + 159 + 354, 199, 1169)
    bananas = next(x for x in p["products"] if x["key"] == "bio bananen")
    assert bananas["total_cents"] == 398 and bananas["lines"] == 2
    assert bananas["quantities"] == {"kg": 2.0} and bananas["average_cents"] == {"kg": 199}
    assert bananas["stores"] == ["LIDL", "REWE"] and bananas["name"] == "BIO BANANEN"
    assert bananas["last_bought"] == (TODAY - timedelta(days=1)).isoformat() and bananas["is_food"]
    assert [x["key"] for x in p["products"]][:2] == ["bio bananen", "mineralwasser"]  # biggest spending first

    # food filter: the products narrow, the sums stay
    food = purchases(client, auth, food="food")
    assert "spuelmittel" not in {x["key"] for x in food["products"]} and food["nonfood_cents"] == 199
    assert [x["key"] for x in purchases(client, auth, food="nonfood")["products"]] == ["spuelmittel"]
    # search, store and category
    assert [x["key"] for x in purchases(client, auth, q="Banane")["products"]] == ["bio bananen"]
    rewe = client.get("/api/v1/stores", headers=auth).json()
    rewe_id = next(s["id"] for s in rewe if s["name"] == "REWE")
    by_store = purchases(client, auth, store_id=rewe_id)
    assert by_store["total_cents"] == 159 + 354 and {x["key"] for x in by_store["products"]} == {"bio bananen", "mineralwasser"}
    drinks = cats(client, auth)["drinks"]["id"]
    assert [x["key"] for x in purchases(client, auth, category_id=drinks)["products"]] == ["mineralwasser"]
    # a longer period finds the old purchase too
    assert next(x for x in purchases(client, auth, range="365d")["products"] if x["key"] == "bio bananen")["lines"] == 3


def test_lines_of_one_product(client, auth, png):
    first = receipt(client, auth, png, "LIDL", TODAY - timedelta(days=3), [("Bio Bananen", 1.2, "kg", 239, "groceries")])
    second = receipt(client, auth, png, "REWE", TODAY - timedelta(days=1), [("Bio Bananen", 0.8, "kg", 159, "groceries")])
    lines = client.get("/api/v1/purchases/lines", headers=auth, params={"key": "bio bananen", "range": "30d"}).json()
    assert [(l["receipt_id"], l["store_name"], l["quantity"], l["unit"]) for l in lines] == [
        (second, "REWE", 0.8, "kg"), (first, "LIDL", 1.2, "kg")]


def test_custom_period_and_bad_input(client, auth, png):
    receipt(client, auth, png, "LIDL", TODAY - timedelta(days=40), [("Brot", 1, "piece", 250, "groceries")])
    start = (TODAY - timedelta(days=45)).isoformat()
    end = (TODAY - timedelta(days=35)).isoformat()
    assert purchases(client, auth, range="custom", start=start, end=end)["food_cents"] == 250
    assert client.get("/api/v1/purchases", headers=auth, params={"range": "custom"}).status_code == 422
    assert client.get("/api/v1/purchases", headers=auth, params={"food": "x"}).status_code == 422
    assert client.get("/api/v1/purchases").status_code == 401


def test_unit_comes_from_the_reader_and_can_be_corrected(client, auth, png):
    [r] = upload(client, auth, png).json()
    units = {i["name"]: (i["quantity"], i["unit"]) for i in r["items"]}
    assert units["Bio Bananen"] == (1.15, "kg") and units["Pfand"] == (1, "piece")
    items = [{**i, "unit": "l"} if i["name"] == "Mineralwasser 6x1,5L" else i for i in r["items"]]
    patched = client.patch(f"/api/v1/receipts/{r['id']}", headers=auth, json={"items": items}).json()
    assert next(i for i in patched["items"] if i["name"] == "Mineralwasser 6x1,5L")["unit"] == "l"
    bad = [{**items[0], "unit": "sack"}] + items[1:]
    assert client.patch(f"/api/v1/receipts/{r['id']}", headers=auth, json={"items": bad}).status_code == 422
