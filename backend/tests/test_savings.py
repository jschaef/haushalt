"""Savings accounts: money moved there counts as saved, once."""

from test_accounts import GIRO, OTHER, SAVINGS, accounts, d, postbank
from test_banking import import_file


def saved(client, auth) -> int:
    return client.get("/api/v1/stats/summary?range=30d", headers=auth).json()["saved_cents"]


def savings_account(client, auth) -> dict:
    return client.post("/api/v1/bank/accounts", headers=auth, json={"name": "Tagesgeld", "iban": SAVINGS, "kind": "savings"}).json()


def test_account_kind(client, auth):
    account = savings_account(client, auth)
    assert account["kind"] == "savings"
    assert client.post("/api/v1/bank/accounts", headers=auth, json={"name": "X", "kind": "depot"}).status_code == 422
    updated = client.put(f"/api/v1/bank/accounts/{account['id']}", headers=auth, json={"name": "Tagesgeld", "iban": SAVINGS, "kind": "giro"})
    assert updated.json()["kind"] == "giro"


def test_transfer_to_savings_counts_as_saved(client, auth):
    # without a savings account nothing is saved, the transfer is just money moved
    import_file(client, auth, postbank(GIRO, (d(3), "Ich", "Sparen", SAVINGS, "-300,00"), (d(2), "Laden", "Kauf", OTHER, "-5,00")))
    assert saved(client, auth) == 0
    savings_account(client, auth)
    assert saved(client, auth) == 30000
    # money taken back lowers it; spending is untouched
    import_file(client, auth, postbank(GIRO, (d(1), "Ich", "Zurück", SAVINGS, "100,00")))
    assert saved(client, auth) == 20000
    assert client.get("/api/v1/stats/summary?range=30d", headers=auth).json()["total_cents"] == 0


def test_both_statements_count_once(client, auth):
    savings_account(client, auth)
    client.post("/api/v1/bank/accounts", headers=auth, json={"name": "Giro", "iban": GIRO})
    import_file(client, auth, postbank(GIRO, (d(3), "Ich", "Sparen", SAVINGS, "-300,00")))
    # the savings statement shows the same money arriving a day later
    import_file(client, auth, postbank(SAVINGS, (d(2), "Ich", "Sparen", GIRO, "300,00"), (d(1), "Ich", "Bar eingezahlt", OTHER, "50,00")))
    assert saved(client, auth) == 30000
    # only the savings statement known: its transfer counts
    import_file(client, auth, postbank(SAVINGS, (d(1), "Ich", "Bonus", GIRO, "25,00")))
    assert saved(client, auth) == 32500
    assert {a["kind"] for a in accounts(client, auth)} == {"giro", "savings"}
