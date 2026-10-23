"""Own bank accounts: recognised from the statement, chosen on import,
transfers between them count nowhere."""

from datetime import date, timedelta

from sqlalchemy import create_engine, inspect, text

from haushalt_api import db as db_module
from haushalt_api.banking import normalize_iban, statement_iban, valid_iban
from test_banking import import_file

# well-known example IBANs with valid check digits
GIRO = "DE89370400440532013000"
SAVINGS = "DE02120300000000202051"
OTHER = "DE44500105175407324931"


def d(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).strftime("%d.%m.%Y")


def postbank(own_iban: str, *rows: tuple[str, str, str, str]) -> bytes:
    """Postbank layout: the own account above the table (values made up)."""
    lines = [
        "Umsätze",
        "Konto;Filial-/Kontonummer;IBAN;Währung",
        f"Giro;000 0000000 00;{own_iban[:4]} {own_iban[4:8]} {own_iban[8:12]} {own_iban[12:16]} {own_iban[16:20]} {own_iban[20:]};EUR",
        "",
        "Buchungstag;Wert;Umsatzart;Begünstigter / Auftraggeber;Verwendungszweck;IBAN / Kontonummer;BIC;Kundenreferenz;"
        "Mandatsreferenz;Gläubiger ID;Fremde Gebühren;Betrag;Abweichender Empfänger;Anzahl der Aufträge;Anzahl der Schecks;Soll;Haben;Währung",
    ]
    lines += [f"{day};{day};Überweisung;{who};{why};{iban};;;;;;{amount};;;;;;EUR" for day, who, why, iban, amount in
              [(r[0], r[1], r[2], r[3], r[4]) for r in rows]]
    return "\n".join(lines).encode("utf-8-sig")


def camt(own_iban: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt><Stmt>
<Acct><Id><IBAN>{own_iban}</IBAN></Id></Acct>
<Ntry><Amt Ccy="EUR">5.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts><BookgDt><Dt>{date.today().isoformat()}</Dt></BookgDt>
<NtryDtls><TxDtls><RltdPties><Cdtr><Nm>Kiosk</Nm></Cdtr></RltdPties><RmtInf><Ustrd>Zeitung</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
</Stmt></BkToCstmrStmt></Document>""".encode()


def accounts(client, auth) -> list[dict]:
    return client.get("/api/v1/bank/accounts", headers=auth).json()


def test_iban_check_digits():
    assert valid_iban(GIRO) and valid_iban(SAVINGS)
    assert not valid_iban("DE89370400440532013001")  # one digit off
    assert not valid_iban("1234") and not valid_iban("")
    assert normalize_iban(" de89 3704 0044 0532 0130 00 ") == GIRO


def test_statement_names_its_account():
    assert statement_iban(postbank(GIRO, (d(1), "Laden", "Kauf", OTHER, "-5,00"))) == GIRO
    assert statement_iban(camt(SAVINGS)) == SAVINGS
    # an IBAN only inside the table (a counterparty) is not the own account
    plain = f"Buchungstag;Empfänger;IBAN;Betrag\n{d(1)};Laden;{OTHER};-5,00\n".encode()
    assert statement_iban(plain) == ""
    assert statement_iban(b"<Document><broken") == ""


def test_import_recognises_and_creates_the_account(client, auth):
    first = import_file(client, auth, postbank(GIRO, (d(2), "Laden", "Kauf 1", OTHER, "-5,00"))).json()
    assert first["account_name"] == "Konto …3000" and first["imported"] == 1
    [account] = accounts(client, auth)
    assert account["iban"] == GIRO and account["bookings"] == 1
    # the next statement of the same account goes to it, no second account
    second = import_file(client, auth, postbank(GIRO, (d(1), "Laden", "Kauf 2", OTHER, "-6,00"))).json()
    assert second["account_id"] == account["id"]
    assert [a["bookings"] for a in accounts(client, auth)] == [2]
    assert {t["account_id"] for t in client.get("/api/v1/bank/transactions", headers=auth).json()} == {account["id"]}
    # CAMT says its account too
    assert import_file(client, auth, camt(SAVINGS), "auszug.xml").json()["account_name"] == "Konto …2051"


def test_chosen_account_learns_the_iban_and_refuses_another(client, auth):
    created = client.post("/api/v1/bank/accounts", headers=auth, json={"name": "Postbank Giro", "bank": "Postbank"}).json()
    files = [("file", ("a.csv", postbank(GIRO, (d(1), "Laden", "Kauf", OTHER, "-5,00")), "text/csv"))]
    result = client.post("/api/v1/bank/import", headers=auth, files=files, data={"account_id": str(created["id"])}).json()
    assert result["account_id"] == created["id"]
    assert accounts(client, auth)[0]["iban"] == GIRO
    # a statement of another account must not land in this one
    files = [("file", ("b.csv", postbank(SAVINGS, (d(1), "Laden", "Kauf", OTHER, "-5,00")), "text/csv"))]
    refused = client.post("/api/v1/bank/import", headers=auth, files=files, data={"account_id": str(created["id"])})
    assert refused.status_code == 409 and SAVINGS in refused.json()["detail"]
    assert len(client.get("/api/v1/bank/transactions", headers=auth).json()) == 1
    files = [("file", ("c.csv", postbank(GIRO), "text/csv"))]
    assert client.post("/api/v1/bank/import", headers=auth, files=files, data={"account_id": "999"}).status_code == 422


def test_transfers_between_own_accounts_count_nowhere(client, auth):
    client.post("/api/v1/bank/accounts", headers=auth, json={"name": "Sparkonto", "iban": SAVINGS})
    result = import_file(
        client, auth,
        postbank(GIRO, (d(2), "Ich", "Sparen", SAVINGS, "-100,00"), (d(1), "Ich", "Zurück", SAVINGS, "50,00"), (d(1), "Laden", "Kauf", OTHER, "-5,00")),
    ).json()
    assert result["transfers"] == 2 and result["ignored"] == 2 and result["review"] == 1
    before = client.get("/api/v1/stats/summary?range=7d", headers=auth).json()["total_cents"]
    assert before == 0


def test_new_account_turns_waiting_bookings_into_transfers(client, auth):
    import_file(client, auth, postbank(GIRO, (d(1), "Ich", "Sparen", SAVINGS, "-100,00")))
    [tx] = client.get("/api/v1/bank/transactions?status=review", headers=auth).json()
    assert tx["iban"] == SAVINGS
    client.post("/api/v1/bank/accounts", headers=auth, json={"name": "Sparkonto", "iban": SAVINGS.lower()})
    assert client.get("/api/v1/bank/transactions?status=review", headers=auth).json() == []


def test_account_validation_and_delete(client, auth):
    assert client.post("/api/v1/bank/accounts", headers=auth, json={"name": "X", "iban": "DE00123"}).json()["detail"] == "invalid_iban"
    giro = client.post("/api/v1/bank/accounts", headers=auth, json={"name": "  Giro  konto ", "iban": GIRO}).json()
    assert giro["name"] == "Giro konto"
    assert client.post("/api/v1/bank/accounts", headers=auth, json={"name": "Doppelt", "iban": GIRO}).status_code == 409
    updated = client.put(f"/api/v1/bank/accounts/{giro['id']}", headers=auth, json={"name": "Postbank", "iban": GIRO, "color": "#0033a0"})
    assert updated.json()["color"] == "#0033a0"
    import_file(client, auth, postbank(GIRO, (d(1), "Laden", "Kauf", OTHER, "-5,00")))
    assert client.delete(f"/api/v1/bank/accounts/{giro['id']}", headers=auth).status_code == 204
    # the bookings stay, without account
    [tx] = client.get("/api/v1/bank/transactions", headers=auth).json()
    assert tx["account_id"] is None
    assert client.get("/api/v1/bank/accounts").status_code == 401


def test_migration_adds_account_column(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE bank_transactions (id INTEGER PRIMARY KEY, booked_on DATE, amount_cents INTEGER, currency VARCHAR(3), "
            "counterparty VARCHAR(256), iban VARCHAR(34), purpose VARCHAR(512), fingerprint VARCHAR(64), status VARCHAR(16), "
            "receipt_id INTEGER, recurring_id INTEGER, category_id INTEGER, created_at TIMESTAMP)"
        ))
    monkeypatch.setattr(db_module, "engine", engine)
    db_module.Base.metadata.create_all(engine)
    db_module._add_missing_columns()
    assert "account_id" in {c["name"] for c in inspect(engine).get_columns("bank_transactions")}
