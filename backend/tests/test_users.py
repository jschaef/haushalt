"""Admin role, one-time passwords, password changes and the password policy."""

import pytest
from conftest import PASSWORD
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from haushalt_api import admin as admin_cli
from haushalt_api import db as db_module
from haushalt_api.db import SessionLocal, User
from haushalt_api.passwords import MIN_LENGTH, one_time_password, problems


def bearer(token: dict) -> dict:
    return {"Authorization": f"Bearer {token['access_token']}"}


def login(client, username: str, password: str):
    return client.post("/api/v1/token", json={"username": username, "password": password})


def add_member(client, auth, username: str = "anna", **extra) -> str:
    response = client.post("/api/v1/users", headers=auth, json={"username": username, "display_name": "Anna", **extra})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["must_change_password"] is True
    return body["one_time_password"]


# --- policy -------------------------------------------------------------------


@pytest.mark.parametrize(
    "password, reason",
    [
        ("kurz-123", "too_short"),
        ("x" * 129 + "Ab1", "too_long"),
        ("iloveyou1234", "common"),
        ("PasswordPassword", "common"),  # the list is compared case-insensitively
        ("aaaaaaaaaaaaaa", "repetitive"),
        ("abababababab", "repetitive"),
        ("123456789012", "repetitive"),
        ("8901234567890", "repetitive"),  # wraps around
        ("qwertzuiopasdf", "repetitive"),
        ("anna-mag-sonnenschein", "personal"),
        ("Mein-Haushalt-Budget", "personal"),
    ],
)
def test_policy_rejects(password, reason):
    assert reason in problems(password, username="anna", display_name="Anna Beispiel")


@pytest.mark.parametrize("password", [PASSWORD, "pferd batterie heftklammer richtig", "Zwölf Zeichen!", "ünïcödé-länge"])
def test_policy_accepts(password):
    assert problems(password, username="anna", display_name="Anna Beispiel") == []


def test_policy_counts_characters_not_bytes():
    # 12 umlauts are 24 bytes but 12 characters
    assert "too_short" not in problems("äöüäöüäöüßßß")
    assert len("äöüäöüäöüßßß") == MIN_LENGTH


def test_one_time_password_shape():
    password = one_time_password()
    assert len(password) == 23 and password.count("-") == 3
    assert problems(password) == []
    assert one_time_password() != password


# --- signup and roles -----------------------------------------------------------


def test_signup_enforces_policy_and_makes_first_user_admin(client):
    weak = client.post("/api/v1/signup", json={"username": "jochen", "password": "jochen-12345"})
    assert weak.status_code == 422
    assert weak.json()["detail"]["code"] == "weak_password"
    assert "personal" in weak.json()["detail"]["reasons"]
    token = client.post("/api/v1/signup", json={"username": "jochen", "password": PASSWORD}).json()
    me = client.get("/api/v1/me", headers=bearer(token)).json()
    assert me["is_admin"] is True and me["must_change_password"] is False


def test_only_admins_manage_members(client, auth):
    password = add_member(client, auth)
    token = login(client, "anna", password).json()
    new = client.post(
        "/api/v1/me/password", headers=bearer(token), json={"current_password": password, "new_password": "Brotkorb-mit-Mohn-7"}
    ).json()
    member = bearer(new)
    anna_id = client.get("/api/v1/me", headers=member).json()["id"]
    jochen_id = client.get("/api/v1/me", headers=auth).json()["id"]
    assert client.post("/api/v1/users", headers=member, json={"username": "bert"}).status_code == 403
    assert client.post(f"/api/v1/users/{jochen_id}/reset-password", headers=member).status_code == 403
    assert client.patch(f"/api/v1/users/{jochen_id}", headers=member, json={"disabled": True}).status_code == 403
    # members still see everybody and all data
    assert len(client.get("/api/v1/users", headers=member).json()) == 2
    assert client.get("/api/v1/receipts", headers=member).status_code == 200
    # an admin can appoint another admin
    assert client.patch(f"/api/v1/users/{anna_id}", headers=auth, json={"is_admin": True}).json()["is_admin"] is True
    assert client.post("/api/v1/users", headers=member, json={"username": "bert"}).status_code == 201


def test_admin_cannot_lock_themselves_out(client, auth):
    me = client.get("/api/v1/me", headers=auth).json()["id"]
    assert client.patch(f"/api/v1/users/{me}", headers=auth, json={"is_admin": False}).status_code == 409
    assert client.patch(f"/api/v1/users/{me}", headers=auth, json={"disabled": True}).status_code == 409
    assert client.post(f"/api/v1/users/{me}/reset-password", headers=auth).status_code == 409
    assert client.patch("/api/v1/users/999", headers=auth, json={"disabled": True}).status_code == 404


# --- one-time password and change ---------------------------------------------------


def test_one_time_password_only_allows_the_change(client, auth):
    password = add_member(client, auth)
    token = login(client, "anna", password)
    assert token.status_code == 200 and token.json()["must_change_password"] is True
    headers = bearer(token.json())
    blocked = client.get("/api/v1/receipts", headers=headers)
    assert blocked.status_code == 403 and blocked.json()["detail"] == "password_change_required"
    assert client.get("/api/v1/bank/transactions", headers=headers).status_code == 403  # routers too
    assert client.get("/api/v1/me", headers=headers).json()["must_change_password"] is True

    wrong = client.post("/api/v1/me/password", headers=headers, json={"current_password": "nope", "new_password": PASSWORD})
    assert wrong.status_code == 403
    same = client.post("/api/v1/me/password", headers=headers, json={"current_password": password, "new_password": password})
    assert same.status_code == 422 and same.json()["detail"]["reasons"] == ["unchanged"]
    weak = client.post("/api/v1/me/password", headers=headers, json={"current_password": password, "new_password": "iloveyou1234"})
    assert weak.status_code == 422 and "common" in weak.json()["detail"]["reasons"]

    changed = client.post("/api/v1/me/password", headers=headers, json={"current_password": password, "new_password": PASSWORD})
    assert changed.status_code == 200 and changed.json()["must_change_password"] is False
    # the old session is over, the returned token works everywhere
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert client.get("/api/v1/receipts", headers=bearer(changed.json())).status_code == 200
    assert login(client, "anna", password).status_code == 401
    assert login(client, "anna", PASSWORD).status_code == 200


def test_password_change_ends_other_sessions(client, auth):
    other_device = bearer(login(client, "jochen", PASSWORD).json())
    new = client.post("/api/v1/me/password", headers=auth, json={"current_password": PASSWORD, "new_password": "Neues-Passwort-fuer-alles"})
    assert new.status_code == 200
    assert client.get("/api/v1/me", headers=other_device).status_code == 401
    assert client.get("/api/v1/me", headers=auth).status_code == 401
    assert client.get("/api/v1/me", headers=bearer(new.json())).status_code == 200


def test_current_password_guesses_are_limited(client, auth):
    for _ in range(5):
        body = {"current_password": "falsch", "new_password": "Neues-Passwort-fuer-alles"}
        assert client.post("/api/v1/me/password", headers=auth, json=body).status_code == 403
    body = {"current_password": PASSWORD, "new_password": "Neues-Passwort-fuer-alles"}
    assert client.post("/api/v1/me/password", headers=auth, json=body).status_code == 429


def test_password_is_no_longer_changed_through_profile(client, auth):
    client.patch("/api/v1/me", headers=auth, json={"password": "Neues-Passwort-fuer-alles"})
    assert login(client, "jochen", "Neues-Passwort-fuer-alles").status_code == 401


# --- reset and disable ---------------------------------------------------------------


def test_reset_gives_new_one_time_password_and_ends_sessions(client, auth):
    first = add_member(client, auth)
    token = login(client, "anna", first).json()
    changed = client.post("/api/v1/me/password", headers=bearer(token), json={"current_password": first, "new_password": "Brotkorb-mit-Mohn-7"})
    member = bearer(changed.json())
    anna_id = client.get("/api/v1/me", headers=member).json()["id"]

    reset = client.post(f"/api/v1/users/{anna_id}/reset-password", headers=auth)
    assert reset.status_code == 200
    one_time = reset.json()["one_time_password"]
    assert reset.json()["user"]["must_change_password"] is True
    assert client.get("/api/v1/me", headers=member).status_code == 401
    assert login(client, "anna", "Brotkorb-mit-Mohn-7").status_code == 401
    assert login(client, "anna", one_time).json()["must_change_password"] is True


def test_disabled_member_cannot_log_in(client, auth):
    password = add_member(client, auth)
    member = bearer(login(client, "anna", password).json())
    anna_id = client.get("/api/v1/me", headers=member).json()["id"]
    assert client.patch(f"/api/v1/users/{anna_id}", headers=auth, json={"disabled": True}).json()["disabled"] is True
    assert client.get("/api/v1/me", headers=member).status_code == 401
    refused = login(client, "anna", password)
    assert refused.status_code == 403 and refused.json()["detail"] == "account_disabled"
    # a wrong password does not reveal that the account is disabled
    assert login(client, "anna", "falsch").status_code == 401
    client.patch(f"/api/v1/users/{anna_id}", headers=auth, json={"disabled": False})
    assert login(client, "anna", password).status_code == 200


# --- migration and command line ---------------------------------------------------------


def test_first_existing_account_becomes_admin(tmp_path, monkeypatch):
    """A database from before the admin role: its first account gets it."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64) UNIQUE, display_name VARCHAR(128), "
            "password_hash VARCHAR(256), locale VARCHAR(8), created_at TIMESTAMP)"
        ))
        connection.execute(text("INSERT INTO users (id, username, display_name, password_hash, locale) VALUES (2, 'b', 'B', 'x', 'de')"))
        connection.execute(text("INSERT INTO users (id, username, display_name, password_hash, locale) VALUES (5, 'a', 'A', 'x', 'de')"))
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    db_module.init_db()
    with db_module.SessionLocal() as session:
        users = {u.username: u for u in session.query(User)}
    assert users["b"].is_admin and not users["a"].is_admin
    assert users["a"].token_version == 0 and not users["a"].disabled


def test_cli_reset_password_and_make_admin(client, auth, capsys):
    add_member(client, auth)
    with SessionLocal() as session:
        session.query(User).filter(User.username == "anna").update({"disabled": True})
        session.commit()
    assert admin_cli.main(["make-admin", "anna"]) == 0
    assert admin_cli.main(["reset-password", "anna"]) == 0
    password = capsys.readouterr().out.split("one-time password for anna: ")[1].split()[0]
    token = login(client, "anna", password).json()
    me = client.get("/api/v1/me", headers=bearer(token)).json()
    assert me["is_admin"] and me["must_change_password"] and not me["disabled"]
    assert admin_cli.main(["reset-password", "nobody"]) == 1
    assert admin_cli.main(["list"]) == 0
    assert "anna admin" in capsys.readouterr().out
