from conftest import PASSWORD
from haushalt_api.auth import create_token, hash_password, verify_password
from haushalt_api.db import User


def test_password_hash_roundtrip():
    stored = hash_password("geheim123")
    assert stored.startswith("scrypt$")
    assert verify_password("geheim123", stored)
    assert not verify_password("falsch", stored)
    assert not verify_password("x", "garbage")


def test_password_hash_normalizes_unicode():
    # NFKC: a full-width "Ａ" and a ligature match their plain forms
    assert verify_password("Abc-ﬁsh-2026", hash_password("Ａbc-fish-2026"))


def test_hashes_from_before_normalization_still_verify():
    import hashlib
    import secrets

    salt = secrets.token_bytes(16)
    raw = "ﬁsh-and-chips-2026"  # differs from its NFKC form
    old = f"scrypt${salt.hex()}${hashlib.scrypt(raw.encode(), salt=salt, n=2**14, r=8, p=1).hex()}"
    assert verify_password(raw, old)


def test_first_signup_then_closed(client):
    assert client.get("/api/v1/setup").json() == {"needs_first_user": True, "signup_open": True}
    assert client.post("/api/v1/signup", json={"username": "anna", "password": PASSWORD}).status_code == 201
    assert client.get("/api/v1/setup").json()["signup_open"] is False
    response = client.post("/api/v1/signup", json={"username": "bert", "password": PASSWORD})
    assert response.status_code == 403


def test_login_and_me(client, auth):
    assert client.post("/api/v1/token", json={"username": "jochen", "password": "wrong"}).status_code == 401
    token = client.post("/api/v1/token", json={"username": "jochen", "password": PASSWORD}).json()
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token['access_token']}"})
    assert me.json()["username"] == "jochen"
    assert me.json()["locale"] == "de"


def test_requires_token(client):
    assert client.get("/api/v1/receipts").status_code == 401
    assert client.get("/api/v1/receipts", headers={"Authorization": "Bearer abc.def"}).status_code == 401


def test_tampered_and_expired_token(client, auth):
    token = auth["Authorization"].split()[1]
    payload, signature = token.rsplit(".", 1)
    bad = {"Authorization": f"Bearer {payload}x.{signature}"}
    assert client.get("/api/v1/me", headers=bad).status_code == 401
    expired = create_token(User(id=1, token_version=0), ttl=-10)["access_token"]
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_logout_revokes(client, auth):
    assert client.post("/api/v1/logout", headers=auth).status_code == 204
    assert client.get("/api/v1/me", headers=auth).status_code == 401


def test_household_members_and_locale(client, auth):
    response = client.post("/api/v1/users", headers=auth, json={"username": "anna"})
    assert response.status_code == 201
    assert client.post("/api/v1/users", headers=auth, json={"username": "anna"}).status_code == 409
    assert [u["username"] for u in client.get("/api/v1/users", headers=auth).json()] == ["anna", "jochen"]
    assert client.patch("/api/v1/me", headers=auth, json={"locale": "en"}).json()["locale"] == "en"
    assert client.patch("/api/v1/me", headers=auth, json={"locale": "fr"}).status_code == 422
