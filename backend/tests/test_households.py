"""Households (tenants) see only their own data: every route that takes an id
answers 404 for another household's id and changes nothing, lists hold only
the own rows, unique names and learned rules are per household."""

from datetime import date, timedelta

import pytest
from conftest import PASSWORD

from haushalt_api.auth import hash_password
from haushalt_api.db import SessionLocal, User, create_household
from test_banking import csv_rows, import_file
from test_users import add_member

DAY = (date.today() - timedelta(days=3)).isoformat()


@pytest.fixture
def other(client, auth):
    """The admin of a second household (auth is household 1)."""
    with SessionLocal() as session:
        create_household(session, "Nachbarn")
        session.add(User(username="nachbar", password_hash=hash_password(PASSWORD), is_admin=True))
        session.commit()
    token = client.post("/api/v1/token", json={"username": "nachbar", "password": PASSWORD}).json()
    return {"Authorization": f"Bearer {token['access_token']}"}


def cats(client, headers) -> dict[str, int]:
    return {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=headers).json()}


@pytest.fixture
def mine(client, auth, png):
    """One of every kind of row in household 1, with the ids."""
    c = cats(client, auth)
    ids = {"category_id": c["groceries"]}
    [receipt] = client.post("/api/v1/receipts", headers=auth, files=[("files", ("b.png", png, "image/png"))]).json()
    ids["receipt_id"] = receipt["id"]
    ids["cost_id"] = client.post("/api/v1/recurring", headers=auth, json={
        "name": "Internet", "category_id": c["subscriptions"], "amount_cents": 4200, "start_on": DAY}).json()["id"]
    ids["account_id"] = client.post("/api/v1/bank/accounts", headers=auth, json={"name": "Giro"}).json()["id"]
    import_file(client, auth, csv_rows((date.today() - timedelta(days=2), "Laden", "Kauf", "-12,00")))
    ids["tx_id"] = client.get("/api/v1/bank/transactions", headers=auth).json()[0]["id"]
    ids["merchant_id"] = client.get("/api/v1/bank/merchants", headers=auth).json()[0]["id"]
    ids["tag_id"] = client.post("/api/v1/tags", headers=auth, json={"name": "Urlaub"}).json()["id"]
    ids["meter_id"] = client.post("/api/v1/meters", headers=auth, json={
        "name": "Strom", "kind": "electricity", "unit": "kWh", "category_id": c["electricity"]}).json()["id"]
    ids["reading_id"] = client.post(f"/api/v1/meters/{ids['meter_id']}/readings", headers=auth, json={"read_on": DAY, "value": 100}).json()["id"]
    ids["tariff_id"] = client.post(f"/api/v1/meters/{ids['meter_id']}/tariffs", headers=auth, json={"valid_from": DAY, "unit_price_ct": 30}).json()["id"]
    ids["bill_id"] = client.post("/api/v1/bills", headers=auth, files=[("file", ("r.pdf", b"%PDF-1.4 fake bill", "application/pdf"))]).json()["id"]
    ids["user_id"] = client.get("/api/v1/me", headers=auth).json()["id"]
    return ids


ROUTES = [
    ("PUT", "/api/v1/categories/{category_id}", {"key": "x_y", "name_de": "X", "name_en": "X"}),
    ("GET", "/api/v1/receipts/{receipt_id}", None),
    ("GET", "/api/v1/receipts/{receipt_id}/file", None),
    ("PATCH", "/api/v1/receipts/{receipt_id}", {"total_cents": 1}),
    ("POST", "/api/v1/receipts/{receipt_id}/confirm", None),
    ("POST", "/api/v1/receipts/{receipt_id}/reread", None),
    ("PUT", "/api/v1/recurring/{cost_id}", {"name": "X", "amount_cents": 1, "start_on": DAY}),
    ("PUT", "/api/v1/bank/accounts/{account_id}", {"name": "X"}),
    ("GET", "/api/v1/bank/transactions/{tx_id}/candidates", None),
    ("PATCH", "/api/v1/bank/transactions/{tx_id}", {"status": "ignored"}),
    ("PUT", "/api/v1/bank/transactions/{tx_id}/one-off", {"one_off": True}),
    ("PUT", "/api/v1/bank/merchants/{merchant_id}", {"keyword": "x", "category_id": 1}),
    ("PUT", "/api/v1/tags/{tag_id}", {"name": "X"}),
    ("PUT", "/api/v1/meters/{meter_id}", {"name": "X", "kind": "gas", "unit": "m3"}),
    ("GET", "/api/v1/meters/{meter_id}/summary", None),
    ("GET", "/api/v1/meters/{meter_id}/readings", None),
    ("POST", "/api/v1/meters/{meter_id}/readings", {"read_on": DAY, "value": 999}),
    ("GET", "/api/v1/meters/{meter_id}/tariffs", None),
    ("POST", "/api/v1/meters/{meter_id}/tariffs", {"valid_from": DAY, "unit_price_ct": 1}),
    ("POST", "/api/v1/meters/{meter_id}/device-token", None),
    ("DELETE", "/api/v1/meters/{meter_id}/device-token", None),
    ("PUT", "/api/v1/meters/{meter_id}/source", {"url": "http://192.0.2.1/x", "path": "a"}),
    ("POST", "/api/v1/meters/{meter_id}/poll", None),
    ("PATCH", "/api/v1/bills/{bill_id}", {"meter_id": None}),
    ("POST", "/api/v1/bills/{bill_id}/apply", None),
    ("GET", "/api/v1/bills/{bill_id}/file", None),
    ("PATCH", "/api/v1/users/{user_id}", {"disabled": True}),
    ("POST", "/api/v1/users/{user_id}/reset-password", None),
    # deleting last: the rows above must survive every other attempt
    ("DELETE", "/api/v1/readings/{reading_id}", None),
    ("DELETE", "/api/v1/tariffs/{tariff_id}", None),
    ("DELETE", "/api/v1/bills/{bill_id}", None),
    ("DELETE", "/api/v1/bank/transactions/{tx_id}", None),
    ("DELETE", "/api/v1/bank/merchants/{merchant_id}", None),
    ("DELETE", "/api/v1/bank/accounts/{account_id}", None),
    ("DELETE", "/api/v1/tags/{tag_id}", None),
    ("DELETE", "/api/v1/recurring/{cost_id}", None),
    ("DELETE", "/api/v1/receipts/{receipt_id}", None),
    ("DELETE", "/api/v1/meters/{meter_id}", None),
]


def test_every_route_with_an_id_is_closed_to_other_households(client, auth, other, mine):
    snapshot = {path: client.get(path, headers=auth).json() for path in LISTS}
    for method, path, body in ROUTES:
        url = path.format(**mine)
        response = client.request(method, url, headers=other, json=body)
        assert response.status_code == 404, (method, url, response.status_code, response.text)
    # household 1 is unchanged
    assert {path: client.get(path, headers=auth).json() for path in LISTS} == snapshot
    assert client.get(f"/api/v1/receipts/{mine['receipt_id']}", headers=auth).status_code == 200


def test_routes_list_covers_the_api():
    """A new route with an id must join ROUTES above."""
    from fastapi.routing import APIRoute

    from haushalt_api import banking_api, operator_api, smartmeter_api, tags_api, utilities_api
    from haushalt_api.main import app

    routes = [r for r in app.router.routes if isinstance(r, APIRoute)]
    for module in (banking_api, operator_api, smartmeter_api, tags_api, utilities_api):
        routes += module.router.routes
    # the operator's routes have tests of their own (test_operator.py)
    with_ids = {(m, r.path) for r in routes if "{" in r.path and not r.path.startswith("/api/v1/operator") for m in r.methods}
    assert with_ids == {(m, p) for m, p, _ in ROUTES}


LISTS = [
    "/api/v1/categories", "/api/v1/receipts", "/api/v1/recurring", "/api/v1/bank/accounts",
    "/api/v1/bank/transactions", "/api/v1/bank/merchants", "/api/v1/tags", "/api/v1/meters",
    "/api/v1/bills", "/api/v1/users", "/api/v1/stores",
]


def test_lists_and_statistics_hold_only_the_own_household(client, auth, other, mine):
    for path in ("/api/v1/receipts", "/api/v1/recurring", "/api/v1/bank/accounts", "/api/v1/bank/transactions",
                 "/api/v1/tags", "/api/v1/meters", "/api/v1/bills"):
        assert client.get(path, headers=other).json() == [], path
    assert [u["username"] for u in client.get("/api/v1/users", headers=other).json()] == ["nachbar"]
    # each household has its own categories and merchant list (seeded)
    assert set(cats(client, other).values()).isdisjoint(cats(client, auth).values())
    assert len(client.get("/api/v1/bank/merchants", headers=other).json()) > 0
    assert client.get("/api/v1/stats/summary?range=30d", headers=other).json()["total_cents"] == 0


def test_names_and_bookings_are_per_household(client, auth, other):
    # the same tag name and the same statement in both households
    assert client.post("/api/v1/tags", headers=auth, json={"name": "Urlaub"}).status_code == 201
    assert client.post("/api/v1/tags", headers=other, json={"name": "Urlaub"}).status_code == 201
    statement = csv_rows((date.today() - timedelta(days=2), "REWE Markt", "Kauf", "-20,00"))
    assert import_file(client, auth, statement).json()["imported"] == 1
    assert import_file(client, other, statement).json()["imported"] == 1
    # usernames stay unique in the whole installation (the login names no household)
    response = client.post("/api/v1/users", headers=other, json={"username": "jochen"})
    assert response.status_code == 409


def test_learning_stays_in_the_household(client, auth, other):
    import_file(client, auth, csv_rows((date.today() - timedelta(days=5), "Bäcker Korn", "Brot", "-4,00")))
    tx = client.get("/api/v1/bank/transactions", headers=auth).json()[0]
    client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "counted", "category_id": cats(client, auth)["groceries"]})
    # household 2 imports the same counterparty: nothing learned there
    import_file(client, other, csv_rows((date.today() - timedelta(days=1), "Bäcker Korn", "Brot", "-4,50")))
    assert client.get("/api/v1/bank/transactions", headers=other).json()[0]["status"] == "review"


def test_settings_are_per_household(client, auth, other):
    client.put("/api/v1/bank/settings", headers=auth, json={"one_off_threshold_cents": 5000})
    assert client.get("/api/v1/bank/settings", headers=other).json()["one_off_threshold_cents"] == 100000
    client.put("/api/v1/stats/since", headers=auth, json={"since": date.today().isoformat()})
    assert client.get("/api/v1/stats/since", headers=other).json() == {"since": None}


def test_members_are_added_to_the_admins_household(client, auth, other):
    add_member(client, other, "lena")
    assert "lena" not in [u["username"] for u in client.get("/api/v1/users", headers=auth).json()]
    assert "lena" in [u["username"] for u in client.get("/api/v1/users", headers=other).json()]


def test_a_device_token_reaches_only_its_meter(client, auth, other, mine):
    token = client.post(f"/api/v1/meters/{mine['meter_id']}/device-token", headers=auth).json()["token"]
    response = client.post("/api/v1/ingest/reading", headers={"Authorization": f"Bearer {token}"}, json={"value": 150})
    assert response.status_code == 201 and response.json()["meter_id"] == mine["meter_id"]
    assert client.get("/api/v1/meters", headers=other).json() == []


def test_admins_rename_their_household(client, auth, other):
    assert client.get("/api/v1/household", headers=auth).json()["name"] == "Mein Haushalt"
    assert client.put("/api/v1/household", headers=auth, json={"name": "  Familie   S. "}).json()["name"] == "Familie S."
    assert client.get("/api/v1/household", headers=other).json()["name"] == "Nachbarn"
    password = add_member(client, auth, "anna")
    token = client.post("/api/v1/token", json={"username": "anna", "password": password}).json()
    member = {"Authorization": f"Bearer {client.post('/api/v1/me/password', headers={'Authorization': 'Bearer ' + token['access_token']}, json={'current_password': password, 'new_password': 'Brotkorb-mit-Mohn-7'}).json()['access_token']}"}
    assert client.put("/api/v1/household", headers=member, json={"name": "X"}).status_code == 403
    assert client.get("/api/v1/household").status_code == 401
