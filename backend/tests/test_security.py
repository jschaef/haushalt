import io

from PIL import Image

from conftest import PASSWORD
from haushalt_api.extraction import ExtractionError, image_tiles, sniff
from haushalt_api.ratelimit import FailureLimiter, login_limiter


def test_sniff_by_content(png):
    assert sniff(png) == "image/png"
    assert sniff(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert sniff(b"%PDF-1.7") == "application/pdf"
    assert sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff(b"<html><script>") is None


def test_upload_ignores_claimed_type(client, auth):
    # HTML claimed to be a JPEG must not be stored and served back
    response = client.post("/api/v1/receipts", headers=auth, files=[("files", ("x.jpg", b"<html>", "image/jpeg"))])
    assert response.status_code == 415


def test_upload_uses_sniffed_type(client, auth, png):
    response = client.post("/api/v1/receipts", headers=auth, files=[("files", ("x.pdf", png, "application/pdf"))])
    assert response.json()[0]["media_type"] == "image/png"


def test_file_response_headers(client, auth, png):
    [receipt] = client.post("/api/v1/receipts", headers=auth, files=[("files", ("a.png", png, "image/png"))]).json()
    response = client.get(f"/api/v1/receipts/{receipt['id']}/file", headers=auth)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]


def test_decompression_bomb(monkeypatch):
    buffer = io.BytesIO()
    Image.new("L", (3000, 3000)).save(buffer, format="PNG")
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1_000_000)
    try:
        image_tiles(buffer.getvalue())
    except ExtractionError as exc:
        assert "too large" in str(exc)
    else:
        raise AssertionError("bomb not rejected")


def test_failure_limiter():
    limiter = FailureLimiter(max_failures=2, block_seconds=60)
    assert not limiter.blocked("a")
    limiter.failure("a")
    limiter.failure("a")
    assert limiter.blocked("a") and not limiter.blocked("b")
    limiter.reset("a")
    assert not limiter.blocked("a")


def test_login_rate_limited(client, auth):
    try:
        for _ in range(5):
            assert client.post("/api/v1/token", json={"username": "jochen", "password": "nope"}).status_code == 401
        # blocked now, even with the right password
        response = client.post("/api/v1/token", json={"username": "jochen", "password": PASSWORD})
        assert response.status_code == 429
    finally:
        login_limiter._failures.clear()


def test_api_docs_disabled(client):
    assert client.get("/api/v1/docs").status_code == 404
    assert client.get("/api/v1/openapi.json").status_code == 404
