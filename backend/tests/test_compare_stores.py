"""Store comparison (Jochen, 2026-11-16): the same product across shops by
the comparison name the model gives every line; per shop the latest regular
price per unit. Older lines get their names once, text only, on request."""

from haushalt_api.db import ReceiptItem, SessionLocal
from haushalt_api import tenancy
from test_price_changes import buy, d
from test_receipts import upload


def compare(client, auth, **params):
    response = client.get("/api/v1/purchases/compare", headers=auth, params={"range": "30d", **params})
    assert response.status_code == 200, response.text
    return response.json()


def by_name(data) -> dict[str, dict]:
    return {p["name"]: p for p in data["products"]}


def test_reading_gives_comparison_names_and_the_editor_keeps_them(client, auth, png):
    [r] = upload(client, auth, png).json()
    names = {i["name"]: i["compare_name"] for i in r["items"]}
    assert names["JA! Frischmilch 3,5% 1L"] == "Vollmilch 3,5 % 1 l" and names["Pfand"] == ""
    items = r["items"]
    # an editor that does not send the field keeps it; one that sends it changes it
    without = [{k: v for k, v in i.items() if k != "compare_name"} for i in items]
    kept = client.patch(f"/api/v1/receipts/{r['id']}", headers=auth, json={"items": without}).json()
    assert [i["compare_name"] for i in kept["items"]] == [i["compare_name"] for i in items]
    changed = [{**i, "compare_name": "Milch 1 l"} if i["name"].startswith("JA!") else i for i in kept["items"]]
    after = client.patch(f"/api/v1/receipts/{r['id']}", headers=auth, json={"items": changed}).json()
    assert after["items"][0]["compare_name"] == "Milch 1 l"
    too_long = [{**changed[0], "compare_name": "x" * 129}]
    assert client.patch(f"/api/v1/receipts/{r['id']}", headers=auth, json={"items": too_long}).status_code == 422


def name(client, auth, ids, compare_name):
    """Set the comparison name of the receipts' single line (as the editor would)."""
    for rid in ids:
        r = client.get(f"/api/v1/receipts/{rid}", headers=auth).json()
        items = [{**i, "compare_name": compare_name} for i in r["items"]]
        assert client.patch(f"/api/v1/receipts/{rid}", headers=auth, json={"items": items}).status_code == 200


def test_latest_regular_price_per_store(client, auth, png):
    milk = [
        buy(client, auth, png, "REWE", d(20), {"name": "JA! Milch 1L", "total_cents": 99}),
        buy(client, auth, png, "REWE", d(3), {"name": "JA! Milch 1L", "total_cents": 109}),   # latest at REWE
        buy(client, auth, png, "LIDL", d(5), {"name": "Milbona Milch 1L", "total_cents": 89}),
        # a promotion: the regular price counts
        buy(client, auth, png, "ALDI", d(2), {"name": "Milsani Milch 1L", "total_cents": 79, "discount_cents": 20}),
    ]
    name(client, auth, milk, "Vollmilch 1 l")
    # one store only: no comparison; another unit: another product
    name(client, auth, [buy(client, auth, png, "REWE", d(2), {"name": "Butter", "total_cents": 199})], "Butter 250 g")
    name(client, auth, [
        buy(client, auth, png, "REWE", d(2), {"name": "Bananen", "quantity": 1.0, "unit": "kg", "total_cents": 199}),
        buy(client, auth, png, "LIDL", d(2), {"name": "Bananen", "quantity": 2, "total_cents": 50}),
    ], "Bananen")

    products = by_name(compare(client, auth))
    assert set(products) == {"Vollmilch 1 l"}
    milk_cmp = products["Vollmilch 1 l"]
    assert [(s["store_name"], s["unit_cents"]) for s in milk_cmp["stores"]] == [("LIDL", 89), ("ALDI", 99), ("REWE", 109)]
    assert milk_cmp["stores"][1]["discount_cents"] == 20 and milk_cmp["stores"][2]["date"] == d(3).isoformat()
    assert (milk_cmp["spread_cents"], milk_cmp["spread_pct"]) == (20, 22.5)
    assert milk_cmp["is_food"] and milk_cmp["unit"] == "piece"
    # search by comparison name or by a printed article text; food filter
    assert set(by_name(compare(client, auth, q="vollmilch"))) == {"Vollmilch 1 l"}
    assert set(by_name(compare(client, auth, q="Milbona"))) == {"Vollmilch 1 l"}
    assert compare(client, auth, q="kaffee")["products"] == []
    assert compare(client, auth, food="nonfood")["products"] == []
    # purchases outside the period do not count
    assert compare(client, auth, range="custom", start=d(30).isoformat(), end=d(10).isoformat())["products"] == []


def test_older_lines_are_named_once(client, auth, png):
    buy(client, auth, png, "REWE", d(4), {"name": "JA! Milch 1L", "total_cents": 99})
    buy(client, auth, png, "LIDL", d(3), {"name": "Milbona Milch 1L", "total_cents": 89})
    buy(client, auth, png, "LIDL", d(3), {"name": "Pfand 0,25", "total_cents": 25, "category": "deposit"})
    # lines read before the comparison names existed
    with SessionLocal() as session, tenancy.unscoped(session):
        for item in session.query(ReceiptItem):
            item.compare_name = None
        session.commit()
    before = compare(client, auth)
    assert before["unnamed"] == 3 and before["products"] == []
    named = client.post("/api/v1/purchases/compare/names", headers=auth).json()
    assert named == {"named": 3, "remaining": 0}
    after = compare(client, auth)
    assert after["unnamed"] == 0 and [p["name"] for p in after["products"]] == ["Milch 1L"]
    # deposit is no product and is not asked again
    assert client.post("/api/v1/purchases/compare/names", headers=auth).json() == {"named": 0, "remaining": 0}


def test_validation_and_login(client, auth):
    assert client.get("/api/v1/purchases/compare", headers=auth, params={"food": "x"}).status_code == 422
    assert client.get("/api/v1/purchases/compare").status_code == 401
    assert client.post("/api/v1/purchases/compare/names").status_code == 401
