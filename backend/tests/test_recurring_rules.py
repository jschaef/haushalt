"""A counterparty linked to a recurring cost by a person is linked again on
the next import, within 20 % of the cost's amount."""

from datetime import date, timedelta

from haushalt_api import db as db_module
from haushalt_api.db import AppState, BankTransaction, RecurringRule, SessionLocal
from test_banking import csv_rows, import_file
from test_utilities import meter  # noqa: F401 (fixture)


def d(days_ago: int) -> date:
    return date.today() - timedelta(days=days_ago)


def cats(client, auth) -> dict[str, int]:
    return {c["key"]: c["id"] for c in client.get("/api/v1/categories", headers=auth).json()}


def cost(client, auth, name: str, cents: int, start_days_ago: int, category: str = "subscriptions", **extra) -> dict:
    body = {"name": name, "category_id": cats(client, auth)[category], "amount_cents": cents, "interval_months": 1, "start_on": d(start_days_ago).isoformat(), **extra}
    return client.post("/api/v1/recurring", headers=auth, json=body).json()


def booking(client, auth, why: str) -> dict:
    return next(t for t in client.get("/api/v1/bank/transactions", headers=auth).json() if t["purpose"] == why)


def link(client, auth, why: str, recurring_id: int):
    tx = booking(client, auth, why)
    return client.patch(f"/api/v1/bank/transactions/{tx['id']}", headers=auth, json={"status": "fixed", "recurring_id": recurring_id})


def test_learned_cost_takes_a_different_amount(client, auth):
    internet = cost(client, auth, "Internet", 4200, 120)
    import_file(client, auth, csv_rows((d(60), "Scheune Internet", "Rechnung 1", "-42,37")))
    assert booking(client, auth, "Rechnung 1")["status"] == "review"
    link(client, auth, "Rechnung 1", internet["id"])
    # the next month comes in linked, also with a slightly different amount
    result = import_file(client, auth, csv_rows((d(30), "Scheune Internet", "Rechnung 2", "-44,90"))).json()
    assert result["fixed"] == 1 and booking(client, auth, "Rechnung 2")["recurring_id"] == internet["id"]
    # more than 20 % off (a back payment): a person decides
    import_file(client, auth, csv_rows((d(1), "Scheune Internet", "Nachzahlung", "-60,00")))
    assert booking(client, auth, "Nachzahlung")["status"] == "review"


def test_closest_of_several_costs_of_one_counterparty(client, auth):
    power = cost(client, auth, "Strom", 6000, 120, "electricity")
    gas = cost(client, auth, "Gas", 9300, 120, "gas")
    import_file(client, auth, csv_rows((d(60), "Knauber", "Strom 1", "-60,00"), (d(60), "Knauber", "Gas 1", "-93,00")))
    # exact amounts match without learning; link a different amount by hand
    assert booking(client, auth, "Gas 1")["recurring_id"] == gas["id"]
    import_file(client, auth, csv_rows((d(45), "Knauber", "Gas 2", "-95,00"), (d(45), "Knauber", "Strom 2", "-61,00")))
    link(client, auth, "Gas 2", gas["id"])
    link(client, auth, "Strom 2", power["id"])
    import_file(client, auth, csv_rows((d(30), "Knauber", "Gas 3", "-96,00"), (d(30), "Knauber", "Strom 3", "-58,00")))
    assert booking(client, auth, "Gas 3")["recurring_id"] == gas["id"]
    assert booking(client, auth, "Strom 3")["recurring_id"] == power["id"]


def test_booking_before_the_cost_counts_in_its_category(client, auth):
    gas = cost(client, auth, "Gas", 9300, 10, "gas")
    import_file(client, auth, csv_rows((d(5), "Knauber Erdgas", "Abschlag neu", "-93,00")))
    link(client, auth, "Abschlag neu", gas["id"])  # already linked by amount; learning it is harmless
    # history from last year: the cost did not run then
    result = import_file(client, auth, csv_rows((d(300), "Knauber Erdgas", "Abschlag alt", "-93,00"))).json()
    old = booking(client, auth, "Abschlag alt")
    assert result["counted"] == 1 and old["status"] == "counted" and old["category_id"] == cats(client, auth)["gas"]


def test_rematch_resolves_waiting_bookings(client, auth):
    internet = cost(client, auth, "Internet", 4200, 120)
    import_file(client, auth, csv_rows((d(60), "Scheune Internet", "Rechnung 1", "-42,37"), (d(30), "Scheune Internet", "Rechnung 2", "-42,37")))
    link(client, auth, "Rechnung 1", internet["id"])
    assert client.post("/api/v1/bank/rematch", headers=auth).json()["matched"] == 1
    assert booking(client, auth, "Rechnung 2")["status"] == "fixed"


def test_new_instalment_keeps_the_learned_payer(client, auth, meter):  # noqa: F811
    old = cost(client, auth, "Alt", 7500, 400, "electricity", meter_id=meter["id"])
    import_file(client, auth, csv_rows((d(60), "Stadtwerke", "Abschlag 1", "-75,50")))
    link(client, auth, "Abschlag 1", old["id"])
    bill = client.post("/api/v1/bills", headers=auth, files=[("file", ("r.pdf", b"%PDF-1.4 fake bill", "application/pdf"))]).json()
    client.post(f"/api/v1/bills/{bill['id']}/apply", headers=auth)
    new = next(c for c in client.get("/api/v1/recurring", headers=auth).json() if c["name"] != "Alt")
    # the new instalment (85 €) is linked for the same payer from today on
    import_file(client, auth, csv_rows((d(0), "Stadtwerke", "Abschlag 2", "-86,00")))
    assert booking(client, auth, "Abschlag 2")["recurring_id"] == new["id"]


def test_links_made_before_are_learned_once(session):
    session.delete(session.get(AppState, "recurring_rules_v1"))
    session.commit()
    from haushalt_api.db import RecurringCost

    if True:
        recurring = RecurringCost(name="Internet", amount_cents=4200, interval_months=1, start_on=d(100))
        session.add(recurring)
        session.flush()
        common = {"booked_on": d(1), "purpose": "", "iban": "", "amount_cents": -4237}
        session.add_all([
            BankTransaction(fingerprint="a", counterparty="Scheune Internet", status="fixed", recurring_id=recurring.id, **common),
            BankTransaction(fingerprint="b", counterparty="Scheune Internet", status="fixed", recurring_id=recurring.id, **common),
        ])
        session.commit()
        db_module.init_db()
        assert [(r.pattern, r.recurring_id) for r in session.query(RecurringRule)] == [("bank:scheune internet", recurring.id)]
