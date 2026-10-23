from datetime import date, timedelta

from haushalt_api.extraction import ExtractionError, FakeExtractor
from haushalt_api import main


def upload(client, auth, png, name="bon.png", media_type="image/png"):
    return client.post("/api/v1/receipts", headers=auth, files=[("files", (name, png, media_type))])


def categories(client, auth):
    return {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=auth).json()}


def test_upload_reads_receipt(client, auth, png):
    response = upload(client, auth, png)
    assert response.status_code == 201, response.text
    [receipt] = response.json()
    assert receipt["status"] == "draft"
    assert receipt["store_name"] == "REWE"
    assert receipt["total_cents"] == 1243
    assert receipt["item_sum_cents"] == 1243
    assert receipt["purchased_on"] == date.today().isoformat()
    keys = {v: k for k, v in categories(client, auth).items()}
    assert [keys[i["category_id"]] for i in receipt["items"]] == ["groceries", "groceries", "drinks", "deposit", "household"]
    file = client.get(f"/api/v1/receipts/{receipt['id']}/file", headers=auth)
    assert file.status_code == 200 and file.content == png


def test_bulk_upload_and_duplicates(client, auth, png):
    response = client.post(
        "/api/v1/receipts",
        headers=auth,
        files=[("files", ("a.png", png, "image/png")), ("files", ("b.pdf", b"%PDF-1.4", "application/pdf"))],
    )
    first, second = response.json()
    assert second["source"] == "pdf"
    # same store, total and date: flagged as probable duplicate of each other
    assert second["duplicates"] == [first["id"]]


def test_rejects_unsupported_type(client, auth):
    assert upload(client, auth, b"hello", "a.txt", "text/plain").status_code == 415


def test_failed_reading_keeps_draft(client, auth, png, monkeypatch):
    class Broken:
        def extract(self, *args):
            raise ExtractionError("Anthropic API not reachable")

    monkeypatch.setattr(main, "get_extractor", lambda: Broken())
    [receipt] = upload(client, auth, png).json()
    assert receipt["error"] == "Anthropic API not reachable"
    assert receipt["items"] == []
    monkeypatch.setattr(main, "get_extractor", lambda: FakeExtractor())
    reread = client.post(f"/api/v1/receipts/{receipt['id']}/reread", headers=auth).json()
    assert reread["error"] == "" and len(reread["items"]) == 5


def test_review_learns_category(client, auth, png):
    ids = categories(client, auth)
    [receipt] = upload(client, auth, png).json()
    items = receipt["items"]
    # the dish soap was put into "household"; the person moves it to "drugstore"
    items[4]["category_id"] = ids["drugstore"]
    response = client.patch(
        f"/api/v1/receipts/{receipt['id']}",
        headers=auth,
        json={"store_name": "Rewe Markt GmbH", "items": items},
    )
    assert response.status_code == 200
    assert response.json()["store_name"] == "REWE"  # same normalized store
    # the next receipt with that article uses the learned rule, not the model
    [second] = upload(client, auth, png).json()
    assert second["items"][4]["category_id"] == ids["drugstore"]
    assert second["items"][0]["category_id"] == ids["groceries"]


def test_unknown_category_rejected(client, auth, png):
    [receipt] = upload(client, auth, png).json()
    receipt["items"][0]["category_id"] = 9999
    response = client.patch(f"/api/v1/receipts/{receipt['id']}", headers=auth, json={"items": receipt["items"]})
    assert response.status_code == 422


def test_confirm_needs_date_and_delete(client, auth, png):
    [receipt] = upload(client, auth, png).json()
    client.patch(f"/api/v1/receipts/{receipt['id']}", headers=auth, json={"purchased_on": None})
    assert client.post(f"/api/v1/receipts/{receipt['id']}/confirm", headers=auth).status_code == 422
    client.patch(f"/api/v1/receipts/{receipt['id']}", headers=auth, json={"purchased_on": "2026-10-01"})
    confirmed = client.post(f"/api/v1/receipts/{receipt['id']}/confirm", headers=auth).json()
    assert confirmed["status"] == "confirmed"
    assert [r["id"] for r in client.get("/api/v1/receipts?status=confirmed", headers=auth).json()] == [receipt["id"]]
    assert client.delete(f"/api/v1/receipts/{receipt['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/receipts/{receipt['id']}", headers=auth).status_code == 404


def test_stores_list(client, auth, png):
    [receipt] = upload(client, auth, png).json()
    client.post(f"/api/v1/receipts/{receipt['id']}/confirm", headers=auth)
    [store] = client.get("/api/v1/stores", headers=auth).json()
    assert store == {"id": store["id"], "name": "REWE", "default_category_id": None, "receipts": 1, "total_cents": 1243}


def test_category_crud(client, auth):
    body = {"key": "pets", "name_de": "Haustiere", "name_en": "Pets", "kind": "variable", "color": "#123456", "icon": "dog"}
    created = client.post("/api/v1/categories", headers=auth, json=body)
    assert created.status_code == 201
    assert client.post("/api/v1/categories", headers=auth, json=body).status_code == 409
    body["name_en"] = "Animals"
    updated = client.put(f"/api/v1/categories/{created.json()['id']}", headers=auth, json=body)
    assert updated.json()["name_en"] == "Animals"
    assert client.post("/api/v1/categories", headers=auth, json={**body, "key": "x y"}).status_code == 422


def test_files_are_deleted_after_the_retention_period(client, auth, png, monkeypatch):
    from haushalt_api import config, receipts as receipts_module
    from haushalt_api.db import SessionLocal

    monkeypatch.setattr(config, "RECEIPT_PHOTO_DAYS", 365)
    today = date.today()
    ids = {}
    for name, days_ago, confirm in [("old", 400, True), ("recent", 100, True), ("old draft", 400, False)]:
        [r] = upload(client, auth, png + name.encode()).json()
        client.patch(f"/api/v1/receipts/{r['id']}", headers=auth, json={"purchased_on": (today - timedelta(days=days_ago)).isoformat()})
        if confirm:
            client.post(f"/api/v1/receipts/{r['id']}/confirm", headers=auth)
        ids[name] = r["id"]
    with SessionLocal() as session:
        assert receipts_module.expire_files(session) == 1
        assert receipts_module.expire_files(session) == 0  # idempotent
    old = client.get(f"/api/v1/receipts/{ids['old']}", headers=auth).json()
    assert old["file_deleted"] is True and old["total_cents"] == 1243 and len(old["items"]) == 5
    assert client.get(f"/api/v1/receipts/{ids['old']}/file", headers=auth).status_code == 410
    assert client.post(f"/api/v1/receipts/{ids['old']}/reread", headers=auth).status_code == 422
    # recent receipts and drafts (still to be reviewed) keep their file
    assert client.get(f"/api/v1/receipts/{ids['recent']}/file", headers=auth).status_code == 200
    assert client.get(f"/api/v1/receipts/{ids['old draft']}/file", headers=auth).status_code == 200
    # 0 keeps files forever
    monkeypatch.setattr(config, "RECEIPT_PHOTO_DAYS", 0)
    with SessionLocal() as session:
        assert receipts_module.expire_files(session) == 0
