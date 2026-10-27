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
os.environ["HAUSHALT_POLL_MINUTES"] = "0"
# SQLite by default; HAUSHALT_TEST_DATABASE_URL runs the same suite against
# PostgreSQL (CI does both). That database is emptied by the tests.
if os.environ.get("HAUSHALT_TEST_DATABASE_URL"):
    os.environ["HAUSHALT_DATABASE_URL"] = os.environ["HAUSHALT_TEST_DATABASE_URL"]
else:
    os.environ.pop("HAUSHALT_DATABASE_URL", None)

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from haushalt_api import tenancy  # noqa: E402
from haushalt_api.db import Base, SessionLocal, create_household, engine, init_db  # noqa: E402
from haushalt_api.main import app  # noqa: E402
from haushalt_api.ratelimit import login_limiter  # noqa: E402

# meets the password policy (12+ characters, not common, no username)
PASSWORD = "Kassenbon-Sommer-2026"

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    """The schema once per run, built by the migrations alone."""
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    init_db()


@pytest.fixture(autouse=True)
def fresh_db(migrated_db):
    # every row goes, the schema stays (migrating per test is slow)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
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
    response = client.post("/api/v1/signup", json={"username": "jochen", "password": PASSWORD})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def session():
    """A session in a household of its own (tests without the API)."""
    with SessionLocal() as s:
        create_household(s, "Test")
        s.commit()
        yield s


def unscoped():
    """A session that sees every household (like the CLI)."""
    return tenancy.unscoped(SessionLocal())


@pytest.fixture
def png():
    return PNG_1PX


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_DATA, ignore_errors=True)
