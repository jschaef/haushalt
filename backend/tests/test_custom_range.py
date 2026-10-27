"""A period typed by a person: start and an optional end (today if left
out). It wins over the household's reset date."""

from datetime import date, timedelta

from test_banking import csv_rows, import_file
from test_income import booking, cats, d, decide


def custom(client, auth, start: date, end: date | None = None):
    url = f"/api/v1/stats/summary?range=custom&start={start.isoformat()}" + (f"&end={end.isoformat()}" if end else "")
    return client.get(url, headers=auth)


def test_custom_period_with_and_without_end(client, auth):
    c = cats(client, auth)
    import_file(client, auth, csv_rows((d(40), "Laden", "Alt", "-300,00"), (d(5), "Laden", "Neu", "-100,00")))
    decide(client, auth, booking(client, auth, "Laden", "Alt"), c["lifestyle"])
    decide(client, auth, booking(client, auth, "Laden", "Neu"), c["lifestyle"])
    s = custom(client, auth, d(45), d(30)).json()
    assert (s["start"], s["end"], s["days"], s["total_cents"]) == (d(45).isoformat(), d(30).isoformat(), 16, 30000)
    assert s["average"]["total"]["day"] == round(30000 / 16)
    # no end: up to today; an end in the future stops today
    assert custom(client, auth, d(10)).json()["end"] == date.today().isoformat()
    assert custom(client, auth, d(10), date.today() + timedelta(days=30)).json()["days"] == 11
    # the chosen period wins over the reset date
    client.put("/api/v1/stats/since", headers=auth, json={"since": d(2).isoformat()})
    assert custom(client, auth, d(45), d(30)).json()["total_cents"] == 30000
    assert client.get("/api/v1/stats/summary?range=30d", headers=auth).json()["total_cents"] == 0


def test_custom_period_rules(client, auth):
    assert client.get("/api/v1/stats/summary?range=custom", headers=auth).status_code == 422
    assert custom(client, auth, d(1), d(5)).status_code == 422
    assert client.get("/api/v1/stats/summary?range=custom&start=gestern", headers=auth).status_code == 422
