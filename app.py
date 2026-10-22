from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from expenses_logic import add_expense, load_expenses, summarize_expenses

ROOT = Path(__file__).resolve().parent
INDEX_FILE = ROOT / "index.html"


class ExpenseHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/api/expenses":
            expenses = load_expenses()
            payload = {"expenses": expenses, "summary": summarize_expenses(expenses)}
            self._send_json(payload)
            return

        if parsed.path in {"/", "/index.html"}:
            self._send_file(INDEX_FILE)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/expenses":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "Request body must be valid JSON."}, status=400)
            return

        try:
            expense = add_expense(
                date_value=payload.get("date", ""),
                store=payload.get("store", ""),
                category=payload.get("category", ""),
                amount=payload.get("amount", 0),
                description=payload.get("description", ""),
            )
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return

        self._send_json({"expense": expense}, status=201)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, file_path: Path) -> None:
        if file_path != INDEX_FILE:
            self.send_response(403)
            self.end_headers()
            return

        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


if __name__ == "__main__":
    host = "0.0.0.0"
    port = 8000
    server = ThreadingHTTPServer((host, port), ExpenseHandler)
    print(f"Expense tracker running at http://{host}:{port}")
    server.serve_forever()
