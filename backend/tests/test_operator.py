"""The operator account (created by the CLI): manages households and their
first admin, sees no household data, and household routes refuse it."""

import pytest
from conftest import PASSWORD

from haushalt_api import admin as admin_cli
from test_users import bearer, login

NEW_PASSWORD = "Leuchtturm-am-Deich-27"


@pytest.fixture
def operator(client, auth, capsys):
    """The operator, with its one-time password replaced (auth: household 1)."""
    assert admin_cli.main(["create-operator", "betreiber"]) == 0
    once = capsys.readouterr().out.split("operator betreiber: ")[1].split()[0]
    token = login(client, "betreiber", once).json()
    assert token["must_change_password"] is True
    changed = client.post("/api/v1/me/password", headers=bearer(token), json={"current_password": once, "new_password": NEW_PASSWORD})
    return bearer(changed.json())


def test_operator_creates_a_household_with_its_admin(client, auth, operator):
    response = client.post("/api/v1/operator/households", headers=operator, json={"name": "  Nachbarn ", "admin_username": "lena"})
    assert response.status_code == 201
    body = response.json()
    assert body["household"]["name"] == "Nachbarn" and [a["username"] for a in body["household"]["admins"]] == ["lena"]
    # the new admin logs in with the one-time password and gets a household of their own
    token = login(client, "lena", body["one_time_password"]).json()
    lena = bearer(client.post("/api/v1/me/password", headers=bearer(token), json={
        "current_password": body["one_time_password"], "new_password": PASSWORD}).json())
    assert client.get("/api/v1/household", headers=lena).json()["name"] == "Nachbarn"
    assert len(client.get("/api/v1/categories", headers=lena).json()) > 0
    assert client.get("/api/v1/receipts", headers=lena).json() == []
    names = {h["name"]: h for h in client.get("/api/v1/operator/households", headers=operator).json()}
    assert set(names) == {"Mein Haushalt", "Nachbarn"} and names["Mein Haushalt"]["members"] == 1
    # usernames stay unique everywhere
    assert client.post("/api/v1/operator/households", headers=operator, json={"name": "X", "admin_username": "jochen"}).status_code == 409


def test_operator_sees_no_household_data(client, auth, operator):
    for path in ("/api/v1/receipts", "/api/v1/categories", "/api/v1/bank/transactions", "/api/v1/users", "/api/v1/household"):
        response = client.get(path, headers=operator)
        assert response.status_code == 403 and response.json()["detail"] == "operator_only", path
    assert client.get("/api/v1/me", headers=operator).json()["is_operator"] is True


def test_only_the_operator_reaches_the_operator_routes(client, auth):
    assert client.get("/api/v1/operator/households", headers=auth).status_code == 403
    assert client.post("/api/v1/operator/households", headers=auth, json={"name": "X", "admin_username": "x"}).status_code == 403
    assert client.get("/api/v1/operator/households").status_code == 401


def test_disabling_a_household_locks_out_its_members(client, auth, operator):
    [household] = client.get("/api/v1/operator/households", headers=operator).json()
    response = client.patch(f"/api/v1/operator/households/{household['id']}", headers=operator, json={"disabled": True})
    assert response.json()["disabled"] is True
    blocked = client.get("/api/v1/receipts", headers=auth)
    assert blocked.status_code == 401 and blocked.json()["detail"] == "household_disabled"
    client.patch(f"/api/v1/operator/households/{household['id']}", headers=operator, json={"disabled": False, "name": "Familie S."})
    assert client.get("/api/v1/household", headers=auth).json()["name"] == "Familie S."


def test_operator_resets_only_a_household_admins_password(client, auth, operator):
    [household] = client.get("/api/v1/operator/households", headers=operator).json()
    admin_id = household["admins"][0]["id"]
    once = client.post(f"/api/v1/operator/users/{admin_id}/reset-password", headers=operator).json()["one_time_password"]
    # old sessions end, the one-time password works once
    assert client.get("/api/v1/receipts", headers=auth).status_code == 401
    assert login(client, "jochen", once).json()["must_change_password"] is True
    operator_id = client.get("/api/v1/me", headers=operator).json()["id"]
    assert client.post(f"/api/v1/operator/users/{operator_id}/reset-password", headers=operator).status_code == 404
    assert client.post("/api/v1/operator/users/999/reset-password", headers=operator).status_code == 404


def test_cli_refuses_a_taken_name(client, auth, capsys):
    assert admin_cli.main(["create-operator", "jochen"]) == 1
    assert admin_cli.main(["list"]) == 0


def test_an_operator_alone_leaves_the_first_signup_open(client, capsys):
    assert admin_cli.main(["create-operator", "betreiber"]) == 0
    assert client.get("/api/v1/setup").json()["needs_first_user"] is True
    first = client.post("/api/v1/signup", json={"username": "jochen", "password": PASSWORD})
    assert first.status_code == 201
    me = client.get("/api/v1/me", headers=bearer(first.json())).json()
    assert me["is_admin"] is True and me["is_operator"] is False
