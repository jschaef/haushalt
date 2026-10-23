import json
import socket
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from sqlalchemy import create_engine, inspect, text

from haushalt_api import config, smartmeter
from haushalt_api import db as db_module
from haushalt_api.smartmeter import SourceError, check_url, number_at

# answers of the fake devices, by path
RESPONSES = {
    # IR reading head with Tasmota (shape as documented for SML scripts; not
    # taken from a real device)
    "/cm": (200, json.dumps({"StatusSNS": {"Time": "2026-10-22T10:00:00", "SML": {"Total_in": 12345.678, "Power_curr": 412}}})),
    # AI-on-the-edge camera (value as string)
    "/json": (200, json.dumps({"main": {"value": "823.4512", "raw": "00823.4512", "error": "no error"}})),
    "/broken": (200, "<html>not json</html>"),
    "/huge": (200, json.dumps({"x": "a" * (smartmeter.MAX_BYTES + 10)})),
    "/error": (500, "{}"),
}


class Device(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/redirect":
            self.send_response(302)
            self.send_header("location", "http://8.8.8.8/")
            self.end_headers()
            return
        status, body = RESPONSES.get(path, (404, "{}"))
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def device():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Device)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_number_at():
    assert number_at({"a": {"b": [1, {"c": "12,5"}]}}, "a.b.1.c") == 12.5
    assert number_at({"v": 3}, "v") == 3.0
    for data, path in [({"a": 1}, "b"), ({"a": True}, "a"), ({"a": "x"}, "a"), ({"a": None}, "a"), ({"a": [1]}, "a.5")]:
        with pytest.raises(SourceError):
            number_at(data, path)


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://localhost:8080/json", "http://192.168.1.20/cm", "http://10.0.0.5", "http://[::1]/"])
def test_check_url_allows_local(url):
    assert check_url(url) == url


@pytest.mark.parametrize(
    "url", ["http://8.8.8.8/", "ftp://192.168.1.2/", "file:///etc/passwd", "http://user:pw@192.168.1.2/", "http://", "http://no-such-host.invalid/"]
)
def test_check_url_refuses(url):
    with pytest.raises(SourceError):
        check_url(url)


def test_public_addresses_only_when_allowed(monkeypatch):
    monkeypatch.setattr(config, "POLL_ALLOW_PUBLIC", True)
    assert check_url("http://8.8.8.8/") == "http://8.8.8.8/"


def test_fetch_value_from_devices(device):
    assert smartmeter.fetch_value(f"{device}/cm?cmnd=Status%2010", "StatusSNS.SML.Total_in") == 12345.678
    assert smartmeter.fetch_value(f"{device}/json", "main.value") == 823.4512


@pytest.mark.parametrize("path, message", [("/broken", "not JSON"), ("/huge", "too large"), ("/error", "500"), ("/redirect", "302")])
def test_fetch_value_failures(device, path, message):
    with pytest.raises(SourceError, match=message):
        smartmeter.fetch_value(f"{device}{path}", "x")


@pytest.fixture
def meter(client, auth):
    body = {"name": "Strom", "kind": "electricity", "unit": "kWh", "meter_number": "", "category_id": None}
    return client.post("/api/v1/meters", headers=auth, json=body).json()


def test_push_with_device_token(client, auth, meter):
    token = client.post(f"/api/v1/meters/{meter['id']}/device-token", headers=auth).json()["token"]
    assert token.startswith("hhm_")
    device = {"Authorization": f"Bearer {token}"}
    first = client.post("/api/v1/ingest/reading", headers=device, json={"value": 100.5})
    assert first.status_code == 201 and first.json()["read_on"] == date.today().isoformat()
    # a later value of the same day replaces the reading
    client.post("/api/v1/ingest/reading", headers=device, json={"value": 101.25})
    readings = client.get(f"/api/v1/meters/{meter['id']}/readings", headers=auth).json()
    assert [(r["value"], r["source"]) for r in readings] == [(101.25, "device")]
    # meters count up
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert client.post("/api/v1/ingest/reading", headers=device, json={"value": 200, "read_at": f"{yesterday}T08:00:00"}).status_code == 422
    listed = client.get("/api/v1/meters", headers=auth).json()[0]
    assert listed["has_device_token"] is True and listed["last_ingest_error"].startswith("Value 200")
    assert listed["last_reading"]["value"] == 101.25


def test_device_token_is_checked_and_revocable(client, auth, meter):
    assert client.post("/api/v1/ingest/reading", json={"value": 1}).status_code == 401
    assert client.post("/api/v1/ingest/reading", headers={"Authorization": "Bearer hhm_wrong"}, json={"value": 1}).status_code == 401
    # a user's login token is no device token
    assert client.post("/api/v1/ingest/reading", headers=auth, json={"value": 1}).status_code == 401
    token = client.post(f"/api/v1/meters/{meter['id']}/device-token", headers=auth).json()["token"]
    newer = client.post(f"/api/v1/meters/{meter['id']}/device-token", headers=auth).json()["token"]
    assert client.post("/api/v1/ingest/reading", headers={"Authorization": f"Bearer {token}"}, json={"value": 1}).status_code == 401
    assert client.post("/api/v1/ingest/reading", headers={"Authorization": f"Bearer {newer}"}, json={"value": 1}).status_code == 201
    client.delete(f"/api/v1/meters/{meter['id']}/device-token", headers=auth)
    assert client.post("/api/v1/ingest/reading", headers={"Authorization": f"Bearer {newer}"}, json={"value": 2}).status_code == 401
    assert client.post("/api/v1/ingest/reading", headers={"Authorization": f"Bearer {newer}"}, json={"value": -1}).status_code == 422


def test_source_and_poll(client, auth, meter, device):
    url = f"/api/v1/meters/{meter['id']}"
    assert client.post(f"{url}/poll", headers=auth).status_code == 422  # no source yet
    assert client.put(f"{url}/source", headers=auth, json={"source_url": "http://8.8.8.8/cm", "source_path": "x"}).status_code == 422
    assert client.put(f"{url}/source", headers=auth, json={"source_url": f"{device}/json", "source_path": ""}).status_code == 422
    assert client.put(f"{url}/source", headers=auth, json={"source_url": f"{device}/json", "source_path": "main.value"}).status_code == 200
    polled = client.post(f"{url}/poll", headers=auth).json()
    assert polled == {"read_on": date.today().isoformat(), "value": 823.4512}
    # the background job reads the same way
    assert smartmeter.poll_all() == 1
    client.put(f"{url}/source", headers=auth, json={"source_url": f"{device}/broken", "source_path": "main.value"})
    failed = client.post(f"{url}/poll", headers=auth)
    assert failed.status_code == 422 and "not JSON" in failed.json()["detail"]
    assert client.get("/api/v1/meters", headers=auth).json()[0]["last_ingest_error"] == "Answer is not JSON"
    # switching off
    assert client.put(f"{url}/source", headers=auth, json={"source_url": "", "source_path": "x"}).json() == {"source_url": "", "source_path": ""}


def test_presets_and_login_required(client, auth):
    assert set(client.get("/api/v1/meters/sources/presets", headers=auth).json()) == {"tasmota", "ai_on_the_edge"}
    assert client.get("/api/v1/meters/sources/presets").status_code == 401


def test_migration_adds_meter_source_columns(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE meters (id INTEGER PRIMARY KEY, name VARCHAR(128), kind VARCHAR(16), unit VARCHAR(16), meter_number VARCHAR(64), category_id INTEGER)"))
        connection.execute(text("INSERT INTO meters (name, kind, unit, meter_number) VALUES ('Alt', 'gas', 'm³', '')"))
    monkeypatch.setattr(db_module, "engine", engine)
    db_module.Base.metadata.create_all(engine)
    db_module._add_missing_columns()
    columns = {c["name"] for c in inspect(engine).get_columns("meters")}
    assert {"ingest_token_hash", "source_url", "source_path", "last_ingest_at", "last_ingest_error"} <= columns
    with engine.connect() as connection:
        assert connection.execute(text("SELECT source_url, ingest_token_hash FROM meters")).one() == ("", "")


def test_http_requests_go_to_the_checked_address(monkeypatch):
    """DNS rebinding: the name is resolved once; the request uses that IP."""
    assert smartmeter.pinned("http://meter.local:8080/json?x=1", "192.168.1.20") == (
        "http://192.168.1.20:8080/json?x=1", {"host": "meter.local:8080"})
    assert smartmeter.pinned("http://meter.local/json", "fd00::1") == ("http://[fd00::1]/json", {"host": "meter.local"})
    assert smartmeter.pinned("https://meter.local/json", "192.168.1.20") == ("https://meter.local/json", {})
    calls = []

    def resolve(host, port, *args):
        calls.append(host)
        # first answer local, every later answer public (a rebinding DNS)
        address = "127.0.0.1" if len(calls) == 1 else "8.8.8.8"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    seen = []

    class Recorder(httpx.BaseTransport):
        def handle_request(self, request):
            seen.append((str(request.url), request.headers["host"]))
            return httpx.Response(200, json={"main": {"value": "5"}})

    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=Recorder(), **kw))
    assert smartmeter.fetch_value("http://rebind.example/json", "main.value") == 5.0
    assert seen == [("http://127.0.0.1/json", "rebind.example")] and calls == ["rebind.example"]
