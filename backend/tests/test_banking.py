from datetime import date, timedelta

import pytest

from haushalt_api.banking import StatementError, parse_amount, parse_camt, parse_csv, parse_date, parse_statement

TODAY = date.today()


def d(days_ago: int) -> date:
    return TODAY - timedelta(days=days_ago)


@pytest.mark.parametrize(
    "text, cents",
    [("-1.234,56", -123456), ("1,234.56", 123456), ("-12,5", -1250), ("12.30 EUR", 1230), ("1.234", 123400),
     ("0,99", 99), ("+7", 700), ("15,00-", -1500), ("-0.05", -5)],
)
def test_parse_amount(text, cents):
    assert parse_amount(text) == cents


def test_parse_amount_rejects_garbage():
    with pytest.raises(StatementError):
        parse_amount("abc")


def test_parse_date():
    assert parse_date("03.10.2026") == date(2026, 10, 3)
    assert parse_date("03.10.26") == date(2026, 10, 3)
    assert parse_date("2026-10-03") == date(2026, 10, 3)
    assert parse_date("2026-10-03T12:30:00") == date(2026, 10, 3)


SPARKASSE = (
    '"Auftragskonto";"Buchungstag";"Valutadatum";"Buchungstext";"Verwendungszweck";"Beguenstigter/Zahlungspflichtiger";"Kontonummer/IBAN";"Betrag";"Waehrung"\n'
    '"DE001";"21.10.26";"21.10.26";"KARTENZAHLUNG";"REWE SAGT DANKE 123";"REWE Markt GmbH";"DE02";"-12,43";"EUR"\n'
    '"DE001";"20.10.26";"20.10.26";"GUTSCHRIFT";"Gehalt";"Arbeitgeber AG";"DE03";"2.500,00";"EUR"\n'
).encode("cp1252")

ING = (
    "Umsatzanzeige;Datei erstellt am: 22.10.2026\n\nIBAN;DE00 0000\n\n"
    "Buchung;Valuta;Auftraggeber/Empfänger;Buchungstext;Verwendungszweck;Saldo;Währung;Betrag;Währung\n"
    "21.10.2026;21.10.2026;dm-drogerie markt;Lastschrift;dm sagt danke;1.000,00;EUR;-7,95;EUR\n"
).encode("utf-8-sig")

DKB = (
    '"Buchungsdatum","Wertstellung","Status","Zahlungspflichtige*r","Zahlungsempfänger*in","Verwendungszweck","Umsatztyp","IBAN","Betrag (€)"\n'
    '"21.10.26","21.10.26","Gebucht","Ich","Amazon Payments","Bestellung 123","Ausgang","DE04","-29,99"\n'
).encode("utf-8")

SOLL_HABEN = "Datum;Empfänger;Verwendungszweck;Soll;Haben\n21.10.2026;Bäckerei Heinz;Brötchen;3,40;\n".encode("utf-8")


def test_parse_sparkasse_csv():
    rewe, salary = parse_csv(SPARKASSE)
    assert (rewe.booked_on, rewe.amount_cents, rewe.counterparty, rewe.purpose) == (date(2026, 10, 21), -1243, "REWE Markt GmbH", "REWE SAGT DANKE 123")
    assert salary.amount_cents == 250000


def test_parse_ing_csv_with_preamble():
    [dm] = parse_csv(ING)
    assert dm.counterparty == "dm-drogerie markt" and dm.amount_cents == -795 and dm.purpose == "dm sagt danke"


def test_parse_dkb_csv():
    [amazon] = parse_csv(DKB)
    assert amazon.counterparty == "Amazon Payments" and amazon.amount_cents == -2999


# Postbank: structure of a real "Kontoumsätze" export (2026-10-23) - UTF-8 with
# BOM, account block and balance lines before the table, a closing balance
# line after it, amounts without currency sign. All values here are made up.
POSTBANK = (
    "Umsätze\n"
    "Konto;Filial-/Kontonummer;IBAN;Währung\n"
    "Postbank Giro plus;000 0000000 00;DE00000000000000000000;EUR\n"
    "\n"
    "01.10.2026 - 23.10.2026\n"
    "Letzter Kontostand;;;;1.000,00;EUR\n"
    "Vorgemerkte und noch nicht gebuchte Umsätze sind nicht Bestandteil dieser Übersicht.\n"
    "Buchungstag;Wert;Umsatzart;Begünstigter / Auftraggeber;Verwendungszweck;IBAN / Kontonummer;BIC;"
    "Kundenreferenz;Mandatsreferenz;Gläubiger ID;Fremde Gebühren;Betrag;Abweichender Empfänger;"
    "Anzahl der Aufträge;Anzahl der Schecks;Soll;Haben;Währung\n"
    "23.10.2026;23.10.2026;SEPA Lastschrift;Beispiel Lotterie GmbH;beispiel.de 123 vom 21.10.2026;"
    "DE11111111111111111111;;REF-1;M-1;DE00ZZZ00000000000;;-9;Beispiel.de;;;-9;;EUR\n"
    "21.10.2026;21.10.2026;Kartenzahlung;EDEKA Center;EDEKA SAGT DANKE;DE22222222222222222222;;;;;;-23,45;;;;-23,45;;EUR\n"
    "20.10.2026;20.10.2026;Gutschrift;Arbeitgeber AG;Gehalt Oktober;DE33333333333333333333;;;;;;1.234,56;;;;;1.234,56;EUR\n"
    "Kontostand;23.10.2026;;;2.202,11;EUR\n"
).encode("utf-8-sig")


def test_parse_postbank_csv():
    lotto, edeka, salary = parse_csv(POSTBANK)
    assert (lotto.booked_on, lotto.amount_cents, lotto.counterparty) == (date(2026, 10, 23), -900, "Beispiel Lotterie GmbH")
    assert lotto.purpose == "beispiel.de 123 vom 21.10.2026" and lotto.iban == "DE11111111111111111111"
    assert (edeka.counterparty, edeka.purpose, edeka.amount_cents) == ("EDEKA Center", "EDEKA SAGT DANKE", -2345)
    # income and the balance lines before/after the table are no expenses
    assert salary.amount_cents == 123456


def test_unknown_header_names_the_first_line():
    with pytest.raises(StatementError, match="Kontostand"):
        parse_csv("Kontostand;irgendwas;x\n1;2;3\n".encode())


def test_parse_debit_credit_columns():
    [bakery] = parse_csv(SOLL_HABEN)
    assert bakery.amount_cents == -340 and bakery.counterparty == "Bäckerei Heinz"


def test_csv_without_header_is_rejected():
    with pytest.raises(StatementError):
        parse_csv(b"just;some;text\n1;2;3\n")


def camt(entries: str, version: str = "053.001.08") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.{version}"><BkToCstmrStmt><Stmt>{entries}</Stmt></BkToCstmrStmt></Document>""".encode()


def entry(amount: str, debit: bool, day: date, name: str, purpose: str, status: str = "BOOK") -> str:
    role = "Cdtr" if debit else "Dbtr"
    return f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>{'DBIT' if debit else 'CRDT'}</CdtDbtInd>
<Sts><Cd>{status}</Cd></Sts><BookgDt><Dt>{day.isoformat()}</Dt></BookgDt>
<NtryDtls><TxDtls><RltdPties><{role}><Pty><Nm>{name}</Nm></Pty></{role}><{role}Acct><Id><IBAN>DE11</IBAN></Id></{role}Acct></RltdPties>
<RmtInf><Ustrd>{purpose}</Ustrd><Ustrd>Teil 2</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""


def test_parse_camt():
    data = camt(entry("12.43", True, date(2026, 10, 21), "REWE", "Karte") + entry("5.00", False, date(2026, 10, 20), "Anna", "Zurück")
                + entry("1.00", True, date(2026, 10, 22), "Pending", "x", status="PDNG"))
    rewe, anna = parse_camt(data)
    assert (rewe.amount_cents, rewe.counterparty, rewe.iban, rewe.purpose) == (-1243, "REWE", "DE11", "Karte Teil 2")
    assert anna.amount_cents == 500 and anna.counterparty == "Anna"
    assert len(parse_statement(camt("", "052.001.02"))) == 0


def test_camt_rejects_entity_attacks():
    bomb = b"""<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]><Document>&lol2;</Document>"""
    with pytest.raises(StatementError):
        parse_camt(bomb)
    xxe = b"""<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]><Document>&x;</Document>"""
    with pytest.raises(StatementError):
        parse_camt(xxe)


# --- API -------------------------------------------------------------------------


def import_file(client, auth, data, name="umsaetze.csv"):
    return client.post("/api/v1/bank/import", headers=auth, files=[("file", (name, data, "text/csv"))])


def confirmed_receipt(client, auth, png, store, total_cents, day):
    [r] = client.post("/api/v1/receipts", headers=auth, files=[("files", ("b.png", png, "image/png"))]).json()
    client.patch(f"/api/v1/receipts/{r['id']}", headers=auth, json={"store_name": store, "total_cents": total_cents, "purchased_on": day.isoformat(), "items": []})
    client.post(f"/api/v1/receipts/{r['id']}/confirm", headers=auth)
    return r["id"]


def csv_rows(*rows):
    lines = ["Buchungstag;Empfänger;Verwendungszweck;Betrag"]
    lines += [f"{day.strftime('%d.%m.%Y')};{who};{why};{amount}" for day, who, why, amount in rows]
    return "\n".join(lines).encode()


def test_import_matches_and_dedupes(client, auth, png):
    rewe = confirmed_receipt(client, auth, png, "REWE", 1243, d(3))
    cats = {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=auth).json()}
    client.post("/api/v1/recurring", headers=auth, json={"name": "Miete", "category_id": cats["housing"], "amount_cents": 95000, "interval_months": 1, "start_on": d(100).isoformat()})
    data = csv_rows(
        (d(1), "REWE Markt GmbH", "Kartenzahlung", "-12,43"),   # receipt bought 2 days earlier
        (d(2), "Vermieter", "Miete Oktober", "-950,00"),          # recurring cost
        (d(2), "Online Shop", "Bestellung", "-30,00"),            # unknown -> review
        (d(2), "Online Shop", "Bestellung", "-30,00"),            # same again: a second, real booking
        (d(5), "Arbeitgeber", "Gehalt", "2500,00"),               # income
    )
    result = import_file(client, auth, data).json()
    assert result == {
        "read": 5, "imported": 5, "duplicates": 0, "receipt": 1, "fixed": 1, "counted": 0, "review": 2, "ignored": 1,
        # a CSV without the own IBAN above the table: no account, no transfers
        "transfers": 0, "settlements": 0, "account_id": None, "account_name": None,
    }
    txs = client.get("/api/v1/bank/transactions", headers=auth).json()
    assert next(t for t in txs if t["status"] == "receipt")["receipt_id"] == rewe
    # importing an overlapping statement again adds nothing
    assert import_file(client, auth, data).json()["duplicates"] == 5


def test_ambiguous_receipts_wait_for_review(client, auth, png):
    a = confirmed_receipt(client, auth, png, "Aldi", 500, d(1))
    confirmed_receipt(client, auth, png, "Lidl", 500, d(1))
    result = import_file(client, auth, csv_rows((d(1), "Bargeldlos", "Kartenzahlung", "-5,00"))).json()
    assert result["review"] == 1
    [tx] = client.get("/api/v1/bank/transactions?status=review", headers=auth).json()
    candidates = client.get(f"/api/v1/bank/transactions/{tx['id']}/candidates", headers=auth).json()
    assert len(candidates) == 2
    decided = client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "receipt", "receipt_id": a}).json()
    assert decided["status"] == "receipt" and decided["receipt_id"] == a


def test_counted_decision_is_learned_and_counts_in_stats(client, auth):
    cats = {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=auth).json()}
    import_file(client, auth, csv_rows((d(2), "Online Shop", "Bestellung 1", "-30,00")))
    [tx] = client.get("/api/v1/bank/transactions?status=review", headers=auth).json()
    before = client.get("/api/v1/stats/summary?range=7d", headers=auth).json()["variable_cents"]
    client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "counted", "category_id": cats["lifestyle"]})
    summary = client.get("/api/v1/stats/summary?range=7d", headers=auth).json()
    assert summary["variable_cents"] == before + 3000
    assert {"name": "Online Shop", "cents": 3000, "count": 1} in summary["by_store"]
    # the next booking from the same counterparty is counted automatically
    result = import_file(client, auth, csv_rows((d(1), "Online Shop", "Bestellung 2", "-12,00"))).json()
    assert result["counted"] == 1


def test_receipt_and_fixed_bookings_do_not_count_twice(client, auth, png):
    confirmed_receipt(client, auth, png, "REWE", 1243, d(1))
    before = client.get("/api/v1/stats/summary?range=7d", headers=auth).json()["total_cents"]
    import_file(client, auth, csv_rows((d(1), "REWE", "Karte", "-12,43")))
    assert client.get("/api/v1/stats/summary?range=7d", headers=auth).json()["total_cents"] == before


def test_deleting_the_receipt_reopens_the_booking(client, auth, png):
    rid = confirmed_receipt(client, auth, png, "REWE", 1243, d(1))
    import_file(client, auth, csv_rows((d(1), "REWE", "Karte", "-12,43")))
    client.delete(f"/api/v1/receipts/{rid}", headers=auth)
    [tx] = client.get("/api/v1/bank/transactions", headers=auth).json()
    assert tx["status"] == "review" and tx["receipt_id"] is None


def test_rematch_after_new_receipt(client, auth, png):
    import_file(client, auth, csv_rows((d(1), "Edeka", "Karte", "-8,80")))
    assert client.post("/api/v1/bank/rematch", headers=auth).json() == {"matched": 0}
    confirmed_receipt(client, auth, png, "Edeka", 880, d(1))
    assert client.post("/api/v1/bank/rematch", headers=auth).json() == {"matched": 1}


def test_decision_validation(client, auth, png):
    import_file(client, auth, csv_rows((d(1), "X", "Y", "-1,00")))
    [tx] = client.get("/api/v1/bank/transactions", headers=auth).json()
    url = f"/api/v1/bank/transactions/{tx['id']}"
    assert client.patch(url, headers=auth, json={"status": "receipt"}).status_code == 422
    assert client.patch(url, headers=auth, json={"status": "counted"}).status_code == 422
    assert client.patch(url, headers=auth, json={"status": "fixed", "recurring_id": 999}).status_code == 422
    assert client.patch(url, headers=auth, json={"status": "bogus"}).status_code == 422
    assert client.patch(url, headers=auth, json={"status": "ignored"}).json()["status"] == "ignored"
    assert client.delete(url, headers=auth).status_code == 204


def test_bad_statement_and_login(client, auth):
    assert import_file(client, auth, b"\x00\x01binary").status_code == 422
    assert client.get("/api/v1/bank/transactions").status_code == 401


def test_all_time_range_starts_with_the_oldest_counted_booking(client, auth):
    cats = {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=auth).json()}
    import_file(client, auth, csv_rows((d(40), "Online Shop", "Alt", "-30,00")))
    [tx] = client.get("/api/v1/bank/transactions", headers=auth).json()
    client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "counted", "category_id": cats["lifestyle"]})
    summary = client.get("/api/v1/stats/summary?range=all", headers=auth).json()
    assert summary["start"] == d(40).isoformat() and summary["total_cents"] == 3000


def test_long_counterparty_is_learned_within_column_limits(client, auth):
    cats = {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=auth).json()}
    name = "Sehr langer Empfaenger " * 20  # > 256 characters after normalizing
    import_file(client, auth, csv_rows((d(2), name, "Bestellung", "-5,00")))
    [tx] = client.get("/api/v1/bank/transactions", headers=auth).json()
    decided = client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "counted", "category_id": cats["lifestyle"]})
    assert decided.status_code == 200
    assert import_file(client, auth, csv_rows((d(1), name, "Bestellung 2", "-6,00"))).json()["counted"] == 1
