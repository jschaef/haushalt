"""Credit cards: the card statement is an account of its own, every card
transaction counts, the giro debit paying the statement counts nowhere."""

from datetime import date, timedelta

from haushalt_api.banking import card_merchant, parse_csv, statement_card
from test_accounts import GIRO, OTHER, accounts, postbank
from test_banking import import_file

CARD = "4000********1234"  # made up, masked like the bank's export


def d(days_ago: int) -> str:
    day = date.today() - timedelta(days=days_ago)
    return f"{day.day}.{day.month}.{day.year}"  # the card export has no leading zeros


def card_csv(statement_days_ago: int, *rows: tuple[str, str, str, str, str]) -> bytes:
    """Layout of a German card export (values made up): card above the table,
    the settlement date, foreign amount - rate - euro amount, a balance line.
    rows: (date, purpose, foreign currency, foreign amount, euro amount)"""
    lines = [
        "Kreditkartentransaktionen",
        "Kreditkarte;Kundennummer;Kartennummer;Karteninhaber",
        f"Visa Card (Kreditkarte);000 0000000;{CARD};MAX MUSTER",
        "",
        f"Abrechnungsdatum: {d(statement_days_ago)}",
        "Belegdatum;Eingangstag;Verwendungszweck;Fremdwährung;Betrag;Kurs;Betrag;Währung",
    ]
    lines += [f"{day};{day};{why};{cur};{foreign};1,10000;{eur};EUR" for day, why, cur, foreign, eur in rows]
    lines.append("Saldo:;;;;;;-76,29;EUR")
    return "\n".join(lines).encode("utf-8")


ROWS = (
    (d(5), "AUSLANDSEINSATZENTGELT", "EUR", "-0,39", "-0,39"),
    (d(5), "SOFTWARE INC, 94104 EXAMPLE.COM, CA, US", "USD", "-23,8", "-21,27"),
    (d(6), "PAYPAL *BEISPIELSHOP, 12345 0000000000, DE", "EUR", "-54,63", "-54,63"),
)


def debit(client, auth) -> dict:
    """The giro booking of -76,29 (the card bookings are smaller)."""
    [tx] = [t for t in client.get("/api/v1/bank/transactions", headers=auth).json() if t["amount_cents"] == -7629]
    return tx


def test_card_statement_is_read_in_euros_with_merchants():
    data = card_csv(0, *ROWS)
    assert statement_card(data) == CARD
    fee, foreign, paypal = parse_csv(data)
    # the euro amount after the exchange rate, not the foreign one
    assert foreign.amount_cents == -2127 and foreign.counterparty == "SOFTWARE INC"
    assert paypal.counterparty == "BEISPIELSHOP" and paypal.purpose.startswith("PAYPAL *")
    assert fee.counterparty == "AUSLANDSEINSATZENTGELT" and fee.amount_cents == -39
    assert {b.statement_on for b in (fee, foreign, paypal)} == {date.today()}
    # the balance line is no booking; a giro statement has no card
    assert statement_card(postbank(GIRO)) == ""
    assert card_merchant("PP*1234 LADEN, BERLIN") == "1234 LADEN" and card_merchant("") == ""


def test_card_gets_its_own_account_and_bookings_count(client, auth):
    result = import_file(client, auth, card_csv(0, *ROWS)).json()
    assert result["imported"] == 3 and result["account_name"] == "Kreditkarte …1234"
    [account] = accounts(client, auth)
    assert account["card_number"] == CARD and account["iban"] == ""
    # the same card again: same account, nothing twice
    again = import_file(client, auth, card_csv(0, *ROWS)).json()
    assert again["duplicates"] == 3 and again["account_id"] == account["id"]
    # a decision is learned per shop, not for PayPal
    [tx] = [t for t in client.get("/api/v1/bank/transactions", headers=auth).json() if t["counterparty"] == "BEISPIELSHOP"]
    categories = client.get("/api/v1/categories", headers=auth).json()
    client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "counted", "category_id": categories[0]["id"]})
    assert client.get("/api/v1/stats/summary?range=30d", headers=auth).json()["total_cents"] == 5463


def test_giro_debit_paying_the_card_is_no_spending(client, auth):
    import_file(client, auth, card_csv(3, *ROWS))
    total = "-76,29"  # 0,39 + 21,27 + 54,63
    result = import_file(
        client, auth,
        postbank(GIRO, (d(1), "Kartenbank", "Kreditkartenabrechnung", OTHER, total), (d(1), "Laden", "Kauf", OTHER, "-76,30")),
    ).json()
    assert result["settlements"] == 1 and result["review"] == 1
    card = next(a for a in accounts(client, auth) if a["card_number"])
    paid = debit(client, auth)
    assert paid["status"] == "ignored" and paid["settles_account_id"] == card["id"]
    # a person's decision replaces the mark
    client.patch(f"/api/v1/bank/transactions/{paid['id']}", headers=auth, json={"status": "review"})
    assert debit(client, auth)["settles_account_id"] is None


def test_card_imported_after_the_giro_debit(client, auth):
    import_file(client, auth, postbank(GIRO, (d(1), "Kartenbank", "Abrechnung", OTHER, "-76,29")))
    # only part of the statement: the sum does not match yet
    assert import_file(client, auth, card_csv(3, *ROWS[:2])).json()["settlements"] == 0
    assert debit(client, auth)["status"] == "review"
    # the full statement: the waiting debit is recognised
    assert import_file(client, auth, card_csv(3, *ROWS)).json()["settlements"] == 1
    assert debit(client, auth)["status"] == "ignored"


def test_debit_far_from_the_statement_date_stays(client, auth):
    import_file(client, auth, card_csv(40, *ROWS))
    import_file(client, auth, postbank(GIRO, (d(1), "Laden", "Kauf", OTHER, "-76,29")))
    assert debit(client, auth)["status"] == "review"


def test_card_statement_must_not_land_in_a_giro_account(client, auth):
    giro = client.post("/api/v1/bank/accounts", headers=auth, json={"name": "Giro", "iban": GIRO}).json()
    files = [("file", ("k.csv", card_csv(0, *ROWS), "text/csv"))]
    refused = client.post("/api/v1/bank/import", headers=auth, files=files, data={"account_id": str(giro["id"])})
    assert refused.status_code == 409 and "1234" in refused.json()["detail"]
    # an empty chosen account learns the card
    empty = client.post("/api/v1/bank/accounts", headers=auth, json={"name": "Visa"}).json()
    ok = client.post("/api/v1/bank/import", headers=auth, files=files, data={"account_id": str(empty["id"])}).json()
    assert ok["account_id"] == empty["id"]
    assert next(a for a in accounts(client, auth) if a["id"] == empty["id"])["card_number"] == CARD
