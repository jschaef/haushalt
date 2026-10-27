"""Personal API tokens: a script on the host uploads receipts and bank
statements and reads what its member reads, nothing else; a token is valid
until it is revoked or the account's sessions end."""

from datetime import date, timedelta

from conftest import PASSWORD

from test_banking import csv_rows
from test_users import add_member, bearer, login


def new_token(client, auth, name="Scanner"):
    response = client.post("/api/v1/api-tokens", headers=auth, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def script(token: dict) -> dict:
    return {"Authorization": f"Bearer {token['token']}"}


def test_token_is_shown_once_and_listed_without_secret(client, auth):
    token = new_token(client, auth, "  Handy   Kurzbefehl ")
    assert token["token"].startswith("hh_") and len(token["token"]) > 40
    assert token["name"] == "Handy Kurzbefehl" and token["hint"] == token["token"][-4:]
    [listed] = client.get("/api/v1/api-tokens", headers=auth).json()
    assert "token" not in listed and listed["last_used_at"] is None
    assert client.post("/api/v1/api-tokens", headers=auth, json={"name": "   "}).status_code == 422


def test_token_uploads_and_reads(client, auth, png):
    token = new_token(client, auth)
    [receipt] = client.post("/api/v1/receipts", headers=script(token), files=[("files", ("b.png", png, "image/png"))]).json()
    assert receipt["status"] == "draft"
    me = client.get("/api/v1/me", headers=auth).json()
    assert client.get(f"/api/v1/receipts/{receipt['id']}", headers=script(token)).json()["uploaded_by"] == me["id"]
    day = date.today() - timedelta(days=2)
    imported = client.post("/api/v1/bank/import", headers=script(token),
                           files=[("file", ("u.csv", csv_rows((day, "Laden", "Kauf", "-12,00")), "text/csv"))])
    assert imported.status_code == 200, imported.text
    assert len(client.get("/api/v1/bank/transactions", headers=script(token)).json()) == 1
    assert client.get("/api/v1/stats/summary", headers=script(token)).status_code == 200
    assert client.get("/api/v1/api-tokens", headers=auth).json()[0]["last_used_at"] is not None


def test_token_changes_nothing_else(client, auth, png):
    token = new_token(client, auth)
    [receipt] = client.post("/api/v1/receipts", headers=auth, files=[("files", ("b.png", png, "image/png"))]).json()
    for method, path, body in [
        ("POST", f"/api/v1/receipts/{receipt['id']}/confirm", None),
        ("DELETE", f"/api/v1/receipts/{receipt['id']}", None),
        ("POST", "/api/v1/tags", {"name": "Urlaub"}),
        ("POST", "/api/v1/users", {"username": "anna"}),
        ("POST", "/api/v1/me/password", {"current_password": PASSWORD, "new_password": "Brotkorb-mit-Mohn-7"}),
        ("POST", "/api/v1/api-tokens", {"name": "noch einer"}),
        ("POST", "/api/v1/logout", None),
    ]:
        response = client.request(method, path, headers=script(token), json=body)
        assert response.status_code in (401, 403), (method, path, response.status_code)
    assert client.get(f"/api/v1/receipts/{receipt['id']}", headers=auth).json()["status"] == "draft"
    # managing tokens needs the browser session, also for reading the list
    assert client.get("/api/v1/api-tokens", headers=script(token)).json()["detail"] == "session_required"


def test_revoked_or_unknown_token_is_rejected(client, auth):
    token = new_token(client, auth)
    assert client.get("/api/v1/me", headers=script(token)).status_code == 200
    assert client.delete(f"/api/v1/api-tokens/{token['id']}", headers=auth).status_code == 204
    assert client.get("/api/v1/me", headers=script(token)).status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer hh_made-up"}).status_code == 401


def test_password_change_and_disabling_end_tokens(client, auth):
    token = new_token(client, auth)
    changed = client.post("/api/v1/me/password", headers=auth, json={"current_password": PASSWORD, "new_password": "Brotkorb-mit-Mohn-7"})
    assert changed.status_code == 200
    assert client.get("/api/v1/me", headers=script(token)).status_code == 401

    password = add_member(client, bearer(changed.json()))
    member = bearer(client.post("/api/v1/me/password", headers=bearer(login(client, "anna", password).json()),
                                json={"current_password": password, "new_password": "Wolkenbruch-im-Mai-42"}).json())
    member_token = new_token(client, member)
    assert client.get("/api/v1/me", headers=script(member_token)).status_code == 200
    anna = next(u for u in client.get("/api/v1/users", headers=bearer(changed.json())).json() if u["username"] == "anna")
    client.patch(f"/api/v1/users/{anna['id']}", headers=bearer(changed.json()), json={"disabled": True})
    assert client.get("/api/v1/me", headers=script(member_token)).status_code == 401


def test_members_see_and_revoke_only_their_own_tokens(client, auth):
    mine = new_token(client, auth)
    password = add_member(client, auth)
    member = bearer(client.post("/api/v1/me/password", headers=bearer(login(client, "anna", password).json()),
                                json={"current_password": password, "new_password": "Wolkenbruch-im-Mai-42"}).json())
    assert client.get("/api/v1/api-tokens", headers=member).json() == []
    assert client.delete(f"/api/v1/api-tokens/{mine['id']}", headers=member).status_code == 404
    assert client.get("/api/v1/me", headers=script(mine)).status_code == 200
