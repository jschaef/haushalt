import os
import shutil
import tempfile
from pathlib import Path

# Configure before the app is imported: a throwaway data directory and the
# fake receipt reader, so no test ever calls the Anthropic API.
_DATA = Path(tempfile.mkdtemp(prefix="haushalt-test-"))
os.environ["HAUSHALT_DATA_DIR"] = str(_DATA)
os.environ["HAUSHALT_EXTRACTOR"] = "fake"
os.environ["HAUSHALT_SECRET"] = "test-secret"
os.environ.pop("HAUSHALT_DATABASE_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from haushalt_api.db import Base, engine, init_db  # noqa: E402
from haushalt_api.main import app  # noqa: E402
from haushalt_api.ratelimit import login_limiter  # noqa: E402

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    login_limiter._failures.clear()
    yield
    shutil.rmtree(_DATA / "receipts", ignore_errors=True)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    """Headers of a logged-in first user."""
    response = client.post("/api/v1/signup", json={"username": "jochen", "password": "secret123"})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def png():
    return PNG_1PX


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_DATA, ignore_errors=True)
