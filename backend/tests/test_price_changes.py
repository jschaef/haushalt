"""Price changes (Jochen, 2026-11-16): the same article (text with pack size)
in the same store against its previous purchase, regular price before the
article's discount, per piece, kg or l."""

from datetime import date, timedelta

from test_purchases import cats
from test_receipts import upload

TODAY = date.today()


def d(days_ago: int) -> date:
    return TODAY - timedelta(days=days_ago)


def buy(client, auth, png, store, day, *items):
    """items: dicts with name, quantity, unit, total_cents and optional
    discount_cents / unit_price_cents / category (key)."""
    c = cats(client, auth)
    [r] = upload(client, auth, png + store.encode() + day.isoformat().encode()).json()
    lines = [
        {"quantity": 1, "unit": "piece", **{k: v for k, v in i.items() if k != "category"},
         "category_id": c[i.get("category", "groceries")]["id"]}
        for i in items
    ]
    total = sum(i["total_cents"] for i in items)
    patched = client.patch(f"/api/v1/receipts/{r['id']}", headers=auth, json={
        "store_name": store, "purchased_on": day.isoformat(), "total_cents": total, "items": lines})
    assert patched.status_code == 200, patched.text
    assert client.post(f"/api/v1/receipts/{r['id']}/confirm", headers=auth).status_code == 200
    return r["id"]


def prices(client, auth, **params):
    response = client.get("/api/v1/purchases/prices", headers=auth, params={"range": "30d", **params})
    assert response.status_code == 200, response.text
    return response.json()["changes"]


def by_name(changes) -> dict[str, dict]:
    return {f"{c['name']}@{c['store_name']}": c for c in changes}


def test_changes_per_article_and_store(client, auth, png):
    milk = {"name": "JA! Milch 1L", "quantity": 2}
    buy(client, auth, png, "REWE", d(60), {**milk, "total_cents": 198})       # 0.99, before the period
    buy(client, auth, png, "REWE", d(10), {**milk, "total_cents": 218})       # 1.09: +10.1 %
    buy(client, auth, png, "REWE", d(5), {**milk, "total_cents": 218})        # unchanged
    # another pack size is another article, another store is no change
    buy(client, auth, png, "REWE", d(4), {"name": "JA! Milch 0,5L", "total_cents": 69})
    buy(client, auth, png, "LIDL", d(3), {"name": "JA! Milch 1L", "total_cents": 79})
    # a promotion is no price drop: regular price = paid + discount
    soap = {"name": "Spülmittel 500ml", "category": "household"}
    buy(client, auth, png, "REWE", d(20), {**soap, "total_cents": 199})
    buy(client, auth, png, "REWE", d(2), {**soap, "total_cents": 149, "discount_cents": 50})
    # weighed goods: printed unit price wins, computed ones tolerate rounding
    buy(client, auth, png, "LIDL", d(15), {"name": "Bananen", "quantity": 1.15, "unit": "kg", "total_cents": 229})
    buy(client, auth, png, "LIDL", d(1), {"name": "Bananen", "quantity": 0.532, "unit": "kg", "total_cents": 106})
    buy(client, auth, png, "LIDL", d(16), {"name": "Tomaten", "quantity": 0.5, "unit": "kg", "total_cents": 150, "unit_price_cents": 299})
    buy(client, auth, png, "LIDL", d(2), {"name": "Tomaten", "quantity": 0.4, "unit": "kg", "total_cents": 140, "unit_price_cents": 349})

    changes = by_name(prices(client, auth))
    assert set(changes) == {"JA! Milch 1L@REWE", "Tomaten@LIDL"}
    milk_change = changes["JA! Milch 1L@REWE"]
    assert (milk_change["old_cents"], milk_change["new_cents"], milk_change["diff_cents"]) == (99, 109, 10)
    assert milk_change["pct"] == 10.1 and milk_change["unit"] == "piece" and milk_change["is_food"]
    assert milk_change["previous_on"] == d(60).isoformat() and milk_change["changed_on"] == d(10).isoformat()
    assert milk_change["last_bought"] == d(5).isoformat() and milk_change["current_cents"] == 109
    assert [h["unit_cents"] for h in milk_change["history"]] == [109, 109, 99]
    tomatoes = changes["Tomaten@LIDL"]
    assert (tomatoes["old_cents"], tomatoes["new_cents"], tomatoes["unit"]) == (299, 349, "kg")
    # biggest change first
    assert list(changes) == ["Tomaten@LIDL", "JA! Milch 1L@REWE"]


def test_filters(client, auth, png):
    buy(client, auth, png, "REWE", d(20), {"name": "Butter", "total_cents": 199})
    buy(client, auth, png, "REWE", d(2), {"name": "Butter", "total_cents": 239})          # +20.1 %
    buy(client, auth, png, "REWE", d(20), {"name": "Kaffee", "total_cents": 999})
    buy(client, auth, png, "REWE", d(2), {"name": "Kaffee", "total_cents": 949})          # -5 %
    buy(client, auth, png, "DM", d(20), {"name": "Zahnpasta", "total_cents": 95, "category": "drugstore"})
    buy(client, auth, png, "DM", d(2), {"name": "Zahnpasta", "total_cents": 105, "category": "drugstore"})
    names = lambda changes: {c["name"] for c in changes}  # noqa: E731
    assert names(prices(client, auth)) == {"Butter", "Kaffee", "Zahnpasta"}
    assert names(prices(client, auth, direction="up")) == {"Butter", "Zahnpasta"}
    assert names(prices(client, auth, direction="down")) == {"Kaffee"}
    assert names(prices(client, auth, min_pct=10)) == {"Butter", "Zahnpasta"}
    assert names(prices(client, auth, food="nonfood")) == {"Zahnpasta"}
    assert names(prices(client, auth, food="food", q="kaffe")) == {"Kaffee"}
    buy(client, auth, png, "REWE", d(20), {"name": "Milch 1L", "total_cents": 99})
    buy(client, auth, png, "REWE", d(2), {"name": "Milch 1L", "total_cents": 109})
    buy(client, auth, png, "REWE", d(20), {"name": "Milch 0,5L", "total_cents": 59})
    buy(client, auth, png, "REWE", d(2), {"name": "Milch 0,5L", "total_cents": 69})
    # the search keeps the pack size: "1L" alone must not match everything
    assert names(prices(client, auth, q="1L")) == {"Milch 1L"}
    assert names(prices(client, auth, q="milch 0,5 l")) == {"Milch 0,5L"}
    dm = next(s["id"] for s in client.get("/api/v1/stores", headers=auth).json() if s["name"] == "DM")
    assert names(prices(client, auth, store_id=dm)) == {"Zahnpasta"}
    # a change before the period is no change in it
    assert prices(client, auth, range="7d", direction="up", q="butter")[0]["changed_on"] == d(2).isoformat()
    assert prices(client, auth, range="custom", start=d(30).isoformat(), end=d(10).isoformat()) == []


def test_validation_and_login(client, auth):
    assert client.get("/api/v1/purchases/prices", headers=auth, params={"direction": "x"}).status_code == 422
    assert client.get("/api/v1/purchases/prices", headers=auth, params={"min_pct": -1}).status_code == 422
    assert client.get("/api/v1/purchases/prices", headers=auth, params={"range": "custom"}).status_code == 422
    assert client.get("/api/v1/purchases/prices").status_code == 401
