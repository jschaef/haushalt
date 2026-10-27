"""The dashboard can start "from now on": an admin sets a reset date, older
data stays stored but no period of the summary reaches before it."""

from datetime import date, timedelta

from test_banking import csv_rows, import_file
from test_income import booking, cats, d, decide, summary
from test_users import add_member, bearer, login


def reset(client, headers, since: date | None):
    return client.put("/api/v1/stats/since", headers=headers, json={"since": since.isoformat() if since else None})


def test_reset_date_starts_the_dashboard(client, auth):
    c = cats(client, auth)
    import_file(client, auth, csv_rows((d(20), "Laden", "Alt", "-300,00"), (d(1), "Laden", "Neu", "-100,00")))
    decide(client, auth, booking(client, auth, "Laden", "Alt"), c["lifestyle"])
    decide(client, auth, booking(client, auth, "Laden", "Neu"), c["lifestyle"])
    assert summary(client, auth)["total_cents"] == 40000

    assert reset(client, auth, d(2)).json() == {"since": d(2).isoformat()}
    s = summary(client, auth)
    assert s["since"] == d(2).isoformat() and s["start"] == d(2).isoformat() and s["days"] == 3
    assert s["total_cents"] == 10000 and s["average"]["total"]["day"] == round(10000 / 3)
    # the previous period lies before the reset date: no comparison
    assert s["previous_total_cents"] == 0
    assert summary(client, auth, "all")["start"] == d(2).isoformat()
    # the bookings stay
    assert len(client.get("/api/v1/bank/transactions", headers=auth).json()) == 2

    # lifted: everything counts again
    assert reset(client, auth, None).json() == {"since": None}
    assert summary(client, auth)["total_cents"] == 40000


def test_reset_date_rules(client, auth):
    assert client.get("/api/v1/stats/since", headers=auth).json() == {"since": None}
    assert reset(client, auth, date.today() + timedelta(days=1)).status_code == 422
    password = add_member(client, auth)
    token = login(client, "anna", password).json()
    member = bearer(client.post(
        "/api/v1/me/password", headers=bearer(token), json={"current_password": password, "new_password": "Brotkorb-mit-Mohn-7"}
    ).json())
    # household-wide: members see it, only admins move it
    assert reset(client, member, date.today()).status_code == 403
    assert client.get("/api/v1/stats/since", headers=member).status_code == 200
    assert client.put("/api/v1/stats/since", json={"since": None}).status_code == 401
