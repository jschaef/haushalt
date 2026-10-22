import json
import tempfile
import unittest
from pathlib import Path

from expenses_logic import add_expense, load_expenses, summarize_expenses


class ExpenseLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_data_file = Path(__file__).resolve().parents[1] / "data" / "expenses.json"
        self.original_data = self.original_data_file.read_text(encoding="utf-8") if self.original_data_file.exists() else None

    def tearDown(self) -> None:
        if self.original_data is not None:
            self.original_data_file.parent.mkdir(parents=True, exist_ok=True)
            self.original_data_file.write_text(self.original_data, encoding="utf-8")
        else:
            if self.original_data_file.exists():
                self.original_data_file.unlink()
        self.temp_dir.cleanup()

    def test_add_expense_updates_categories_and_total(self):
        self.original_data_file.parent.mkdir(parents=True, exist_ok=True)
        self.original_data_file.write_text(json.dumps([], indent=2), encoding="utf-8")

        expense = add_expense("2026-10-15", "Aldi", "food", "16.75", "Weekly groceries")

        self.assertEqual(expense["store"], "Aldi")
        self.assertEqual(expense["category"], "food")
        self.assertEqual(expense["amount"], "16.75")

        expenses = load_expenses()
        summary = summarize_expenses(expenses)
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["total"], "16.75")
        self.assertEqual(summary["by_category"]["food"], "16.75")

    def test_invalid_amount_is_rejected(self):
        with self.assertRaises(ValueError):
            add_expense("2026-10-15", "Energie GmbH", "utilities", "0")


if __name__ == "__main__":
    unittest.main()
