"""One-offs (a gift, a car) are marked by a person and counted apart: in no
category, average, balance or chart; the summary reports their sums."""

from test_banking import csv_rows, import_file
from test_income import booking, cats, d, decide, summary


def mark(client, auth, tx: dict, one_off: bool = True):
    return client.put(f"/api/v1/bank/transactions/{tx['id']}/one-off", headers=auth, json={"one_off": one_off})


def test_one_offs_count_apart(client, auth):
    c = cats(client, auth)
    import_file(client, auth, csv_rows(
        (d(5), "Arbeitgeber", "Gehalt", "2500,00"),
        (d(4), "Tante", "Geschenk", "10000,00"),
        (d(3), "Autohaus", "Auto", "-8000,00"),
        (d(2), "Laden", "Kauf", "-500,00"),
    ))
    decide(client, auth, booking(client, auth, "Arbeitgeber"), c["salary"])
    decide(client, auth, booking(client, auth, "Laden"), c["lifestyle"])
    decide(client, auth, booking(client, auth, "Autohaus"), c["lifestyle"])
    # the gift still waits for review: marking it moves it out of the open sums
    assert mark(client, auth, booking(client, auth, "Tante")).json()["one_off"] is True
    assert mark(client, auth, booking(client, auth, "Autohaus")).status_code == 200
    s = summary(client, auth)
    assert s["income_cents"] == 250000 and s["total_cents"] == 50000 and s["balance_cents"] == 200000
    assert s["open"]["in_cents"] == 0
    assert s["one_off"] == {"in_cents": 1000000, "out_cents": 800000, "count": 2}
    assert sum(day["cents"] for day in s["daily"]) == 50000
    assert sum(m["spending_cents"] for m in s["monthly"]) == 50000
    # unmarked, the car counts again
    mark(client, auth, booking(client, auth, "Autohaus"), False)
    assert summary(client, auth)["total_cents"] == 850000


def test_rematch_and_decisions_keep_the_flag(client, auth):
    c = cats(client, auth)
    import_file(client, auth, csv_rows((d(3), "Autohaus", "Auto", "-8000,00")))
    tx = booking(client, auth, "Autohaus")
    mark(client, auth, tx)
    decide(client, auth, tx, c["lifestyle"])
    client.post("/api/v1/bank/rematch", headers=auth)
    assert booking(client, auth, "Autohaus")["one_off"] is True


def test_threshold_setting(client, auth):
    assert client.get("/api/v1/bank/settings", headers=auth).json() == {"one_off_threshold_cents": 100000}
    assert client.put("/api/v1/bank/settings", headers=auth, json={"one_off_threshold_cents": 50000}).status_code == 200
    assert client.get("/api/v1/bank/settings", headers=auth).json()["one_off_threshold_cents"] == 50000
    assert client.put("/api/v1/bank/settings", headers=auth, json={"one_off_threshold_cents": -1}).status_code == 422


def test_one_off_needs_login(client):
    assert client.get("/api/v1/bank/settings").status_code == 401
    assert client.put("/api/v1/bank/transactions/1/one-off", json={"one_off": True}).status_code == 401
