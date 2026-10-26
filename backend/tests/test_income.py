"""Income against spending: income categories for incoming bookings,
refunds lowering spending, open bookings and months in the summary."""

from datetime import date, timedelta

from haushalt_api import db as db_module
from haushalt_api.db import AppState, BankAccount, BankTransaction, SessionLocal
from test_banking import csv_rows, import_file

GIRO = "DE89370400440532013000"


def d(days_ago: int) -> date:
    return date.today() - timedelta(days=days_ago)


def cats(client, auth) -> dict[str, int]:
    return {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=auth).json()}


def booking(client, auth, who: str, why: str = "") -> dict:
    return next(t for t in client.get("/api/v1/bank/transactions", headers=auth).json() if t["counterparty"] == who and why in t["purpose"])


def decide(client, auth, tx: dict, category_id: int):
    return client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "counted", "category_id": category_id})


def summary(client, auth, range_key: str = "30d") -> dict:
    return client.get(f"/api/v1/stats/summary?range={range_key}", headers=auth).json()


def test_income_categories_exist(client, auth):
    kinds = {c["key"]: c["kind"] for c in client.get("/api/v1/categories", headers=auth).json()}
    assert kinds["salary"] == "income" and kinds["other_income"] == "income" and kinds["groceries"] == "variable"


def test_salary_is_income_and_learned_for_the_payer(client, auth):
    import_file(client, auth, csv_rows((d(3), "Arbeitgeber", "Gehalt Oktober", "2500,00"), (d(2), "Laden", "Kauf", "-500,00")))
    c = cats(client, auth)
    assert booking(client, auth, "Arbeitgeber")["status"] == "review"
    assert decide(client, auth, booking(client, auth, "Arbeitgeber"), c["salary"]).status_code == 200
    decide(client, auth, booking(client, auth, "Laden"), c["lifestyle"])
    s = summary(client, auth)
    assert s["income_cents"] == 250000 and s["total_cents"] == 50000
    assert s["balance_cents"] == 200000 and s["savings_rate"] == 0.8
    assert s["by_income"][0]["key"] == "salary"
    # income is no spending category
    assert "salary" not in {row["key"] for row in s["by_category"]}
    # the next salary of the same payer counts by itself
    result = import_file(client, auth, csv_rows((d(1), "Arbeitgeber", "Gehalt November", "2600,00"))).json()
    assert result["counted"] == 1
    assert summary(client, auth)["income_cents"] == 510000


def test_refund_lowers_spending_of_its_category(client, auth):
    c = cats(client, auth)
    import_file(client, auth, csv_rows((d(5), "Versand", "Bestellung", "-100,00"), (d(2), "Versand", "Retoure", "40,00")))
    decide(client, auth, booking(client, auth, "Versand", "Bestellung"), c["clothing"])
    # imported together with the purchase, the refund waits for its own decision
    refund = booking(client, auth, "Versand", "Retoure")
    assert refund["status"] == "review"
    decide(client, auth, refund, c["clothing"])
    s = summary(client, auth)
    assert s["total_cents"] == 6000 and s["income_cents"] == 0
    assert {row["key"]: row["cents"] for row in s["by_category"]}["clothing"] == 6000
    assert s["savings_rate"] is None


def test_income_category_never_counts_a_payment(client, auth):
    c = cats(client, auth)
    import_file(client, auth, csv_rows((d(3), "Arbeitgeber", "Gehalt", "2500,00"), (d(2), "Arbeitgeber", "Rückzahlung Vorschuss", "-100,00")))
    refused = decide(client, auth, booking(client, auth, "Arbeitgeber", "Rückzahlung"), c["salary"])
    assert refused.status_code == 422 and refused.json()["detail"] == "income_category_for_payment"
    decide(client, auth, booking(client, auth, "Arbeitgeber", "Gehalt"), c["salary"])
    # the payer's learned income category is not used for money going out
    import_file(client, auth, csv_rows((d(1), "Arbeitgeber", "Kantine", "-5,00")))
    assert booking(client, auth, "Arbeitgeber", "Kantine")["status"] == "review"


def test_open_bookings_are_reported_apart(client, auth):
    import_file(client, auth, csv_rows((d(2), "Unbekannt", "?", "-70,00"), (d(1), "Jemand", "?", "30,00")))
    s = summary(client, auth)
    assert s["open"] == {"count": 2, "out_cents": 7000, "in_cents": 3000}
    assert s["total_cents"] == 0 and s["income_cents"] == 0


def test_months_of_the_period(client, auth):
    c = cats(client, auth)
    today = date.today()
    last_month_end = today.replace(day=1) - timedelta(days=1)
    import_file(client, auth, csv_rows((last_month_end, "Arbeitgeber", "Gehalt", "1000,00"), (today, "Laden", "Kauf", "-10,00")))
    decide(client, auth, booking(client, auth, "Arbeitgeber"), c["salary"])
    decide(client, auth, booking(client, auth, "Laden"), c["lifestyle"])
    months = summary(client, auth, "all")["monthly"]
    assert [m["month"] for m in months] == [last_month_end.strftime("%Y-%m"), today.strftime("%Y-%m")]
    assert months[0]["income_cents"] == 100000 and months[-1]["spending_cents"] == 1000


def test_incoming_bookings_ignored_before_are_reopened_once():
    with SessionLocal() as session:
        session.delete(session.get(AppState, "income_v1"))
        session.add(BankAccount(name="Spar", iban=GIRO))
        common = {"booked_on": d(1), "counterparty": "", "purpose": "", "status": "ignored"}
        session.add_all([
            BankTransaction(fingerprint="a", amount_cents=1000, iban="", **common),            # income -> review
            BankTransaction(fingerprint="b", amount_cents=1000, iban="DE89 3704 0044 0532 0130 00", **common),  # transfer
            BankTransaction(fingerprint="c", amount_cents=-500, iban="", **common),            # payment ignored by a person
        ])
        session.commit()
        db_module._reopen_income(session)
        session.commit()
        status = {tx.fingerprint: tx.status for tx in session.query(BankTransaction)}
        assert status == {"a": "review", "b": "ignored", "c": "ignored"}
        # once only: a later decision to ignore stays
        session.query(BankTransaction).filter_by(fingerprint="a").one().status = "ignored"
        session.commit()
        db_module._reopen_income(session)
        assert session.query(BankTransaction).filter_by(fingerprint="a").one().status == "ignored"
