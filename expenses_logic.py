from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent / "data" / "expenses.json"

CATEGORY_LABELS = {
    "household": "Household",
    "utilities": "Utilities",
    "insurance": "Insurance",
    "children": "Children",
    "lifestyle": "Lifestyle",
    "transport": "Transport",
    "food": "Food",
    "other": "Other",
}

DEFAULT_EXPENSES = [
    {
        "id": "sample-water",
        "date": "2026-10-01",
        "store": "Stadtwerke",
        "category": "utilities",
        "amount": "42.15",
        "description": "Water and sewage",
    },
    {
        "id": "sample-gas",
        "date": "2026-10-02",
        "store": "Gas AG",
        "category": "utilities",
        "amount": "76.80",
        "description": "House gas bill",
    },
    {
        "id": "sample-rent",
        "date": "2026-10-03",
        "store": "Home Rental",
        "category": "household",
        "amount": "980.00",
        "description": "Monthly rent",
    },
    {
        "id": "sample-school",
        "date": "2026-10-06",
        "store": "Kinderwelt",
        "category": "children",
        "amount": "58.25",
        "description": "School supplies for daughters",
    },
    {
        "id": "sample-life",
        "date": "2026-10-08",
        "store": "Lidl",
        "category": "lifestyle",
        "amount": "64.99",
        "description": "Groceries and personal care",
    },
]


def _ensure_data_file() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text(json.dumps(DEFAULT_EXPENSES, indent=2), encoding="utf-8")


def load_expenses() -> list[dict[str, Any]]:
    _ensure_data_file()
    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Expense data must be a list.")
    return data


def save_expenses(expenses: list[dict[str, Any]]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(expenses, f, indent=2)


def _decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (TypeError, InvalidOperation, ValueError):
        return Decimal("0")


def add_expense(date_value: str, store: str, category: str, amount: Any, description: str = "") -> dict[str, Any]:
    normalized_category = category.strip().lower()
    if normalized_category not in CATEGORY_LABELS:
        raise ValueError(f"Unsupported category: {category}")

    amount_decimal = _decimal_or_zero(amount)
    if amount_decimal <= 0:
        raise ValueError("Amount must be greater than zero.")

    date_value = str(date_value).strip()
    try:
        date.fromisoformat(date_value)
    except ValueError as exc:  # pragma: no cover - guard against invalid user input
        raise ValueError("Date must be in ISO format YYYY-MM-DD.") from exc

    record = {
        "id": f"expense-{len(load_expenses()) + 1}-{abs(hash(date_value + store + str(amount_decimal)))}",
        "date": date_value,
        "store": store.strip() or "Unknown store",
        "category": normalized_category,
        "amount": format(amount_decimal, "f"),
        "description": description.strip() or "No description",
    }
    expenses = load_expenses()
    expenses.insert(0, record)
    save_expenses(expenses)
    return record


def summarize_expenses(expenses: list[dict[str, Any]]) -> dict[str, Any]:
    totals_by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    totals_by_store: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    total = Decimal("0")

    for expense in expenses:
        amount = _decimal_or_zero(expense.get("amount"))
        total += amount
        category = str(expense.get("category", "other")).lower()
        store = str(expense.get("store", "Unknown store")).strip() or "Unknown store"
        totals_by_category[category] += amount
        totals_by_store[store] += amount

    summary = {
        "total": format(total, "f"),
        "count": len(expenses),
        "by_category": {
            key: format(value, "f")
            for key, value in sorted(totals_by_category.items(), key=lambda item: item[0])
        },
        "by_store": {
            key: format(value, "f")
            for key, value in sorted(totals_by_store.items(), key=lambda item: item[0])
        },
    }
    return summary


def get_category_label(category: str) -> str:
    return CATEGORY_LABELS.get(str(category).lower(), "Other")
