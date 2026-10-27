"""Start the API for the Playwright tests: empty data directory, fake reader.

    python -m haushalt_api.e2e_server --port 8300
"""

import argparse
import os
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8300)
args = parser.parse_args()

os.environ["HAUSHALT_DATA_DIR"] = tempfile.mkdtemp(prefix="haushalt-e2e-")
os.environ["HAUSHALT_EXTRACTOR"] = "fake"
os.environ.setdefault("HAUSHALT_SECRET", "e2e-secret")
os.environ["HAUSHALT_POLL_MINUTES"] = "0"
os.environ.pop("HAUSHALT_DATABASE_URL", None)

import uvicorn  # noqa: E402

from haushalt_api.auth import hash_password  # noqa: E402
from haushalt_api.db import SessionLocal, User, init_db  # noqa: E402

# an operator for the operator page (e2e/operator.spec.ts); real installations
# create theirs with python -m haushalt_api.admin create-operator
init_db()
with SessionLocal() as session:
    session.add(User(username="betreiber", display_name="Betreiber", password_hash=hash_password("Leuchtturm-am-Deich-27"), is_operator=True))
    session.commit()

uvicorn.run("haushalt_api.main:app", host="127.0.0.1", port=args.port, log_level="warning")
