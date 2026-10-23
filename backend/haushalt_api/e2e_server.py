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

uvicorn.run("haushalt_api.main:app", host="127.0.0.1", port=args.port, log_level="warning")
