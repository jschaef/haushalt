"""Receipt details (Jochen, 2026-10-28): a discount printed under an article
belongs to it, time, receipt number and TSE transaction are kept when
printed, and a receipt read twice (same store and TSE transaction) is not
stored again while two real purchases stay apart."""

from haushalt_api.extraction import FAKE_TSE, parse_result, receipt_schema
from test_receipts import upload


def raw(**extra):
    return {
        "is_receipt": True, "store_name": "LIDL", "purchased_on": "2026-10-28", "currency": "EUR", "total": 1.99,
        "payment_method": "card",
        "items": [{"name": "Katenschinken", "quantity": 1, "unit_price": None, "total": 2.29, "discount": 0.30,
                   "discount_label": "Preisvorteil", "category": "groceries"}],
        **extra,
    }


def test_discount_belongs_to_its_article():
    [item] = parse_result(raw()).items
    assert (item.name, item.total_cents, item.discount_cents, item.discount_label) == ("Katenschinken", 199, 30, "Preisvorteil")
    # a negative number from the model is the same discount
    [item] = parse_result(raw(items=[{**raw()["items"][0], "discount": -0.3}])).items
    assert (item.total_cents, item.discount_cents) == (199, 30)


def test_printed_details_are_read_and_missing_ones_stay_empty():
    result = parse_result(raw(purchased_time="18:05", receipt_number=" 4711 ", tse_transaction="12 345", tse_serial="ab:cd"))
    assert (result.purchased_at.isoformat(), result.receipt_number, result.tse_transaction, result.tse_serial) == (
        "18:05:00", "4711", "12 345", "ab:cd")
    # not printed, unreadable or not in the answer at all: no error, just empty
    for extra in ({}, {"purchased_time": None, "tse_transaction": None}, {"purchased_time": "abends", "receipt_number": ""}):
        result = parse_result(raw(**extra))
        assert result.purchased_at is None and result.tse_transaction == "" and result.receipt_number == ""
    item = parse_result(raw(items=[{"name": "Brot", "total": 1.5}])).items[0]
    assert (item.total_cents, item.discount_cents, item.discount_label) == (150, 0, "")


def test_schema_asks_for_the_details():
    schema = receipt_schema(["groceries"])
    assert {"purchased_time", "receipt_number", "tse_transaction", "tse_serial"} <= set(schema["required"])
    assert {"discount", "discount_label"} <= set(schema["properties"]["items"]["items"]["required"])


def test_upload_keeps_discount_time_and_numbers(client, auth, png):
    [receipt] = upload(client, auth, png).json()
    bananas = next(i for i in receipt["items"] if i["name"] == "Bio Bananen")
    assert (bananas["total_cents"], bananas["discount_cents"], bananas["discount_label"]) == (199, 30, "Preisvorteil")
    # the paid amounts still add up to the total
    assert receipt["item_sum_cents"] == receipt["total_cents"] == 1243
    assert (receipt["purchased_at"], receipt["receipt_number"], receipt["tse_transaction"]) == ("18:05:00", "4711", "")

    items = [{**i, "discount_cents": 50, "total_cents": 179} if i["name"] == "Bio Bananen" else i for i in receipt["items"]]
    patched = client.patch(f"/api/v1/receipts/{receipt['id']}", headers=auth, json={
        "items": items, "purchased_at": "09:30", "receipt_number": "0815", "total_cents": 1223}).json()
    bananas = next(i for i in patched["items"] if i["name"] == "Bio Bananen")
    assert (bananas["total_cents"], bananas["discount_cents"]) == (179, 50)
    assert (patched["purchased_at"], patched["receipt_number"]) == ("09:30:00", "0815")


def test_the_same_receipt_read_twice_is_not_stored_again(client, auth, png):
    first = upload(client, auth, png + FAKE_TSE + b"1001").json()[0]
    assert first["tse_transaction"] == "1001" and first["already_present"] is False
    # another photo of the same receipt: same store and TSE transaction
    again = upload(client, auth, png + b"\x00" + FAKE_TSE + b"1001")
    assert again.status_code == 201
    [existing] = again.json()
    assert existing["id"] == first["id"] and existing["already_present"] is True
    assert [r["id"] for r in client.get("/api/v1/receipts", headers=auth).json()] == [first["id"]]


def test_two_real_purchases_of_the_same_things_stay_apart(client, auth, png):
    first = upload(client, auth, png + FAKE_TSE + b"2001").json()[0]
    second = upload(client, auth, png + FAKE_TSE + b"2002").json()[0]
    assert second["id"] != first["id"] and second["already_present"] is False
    # same store, total and day, but another TSE transaction: no warning
    assert second["duplicates"] == []
    assert client.get(f"/api/v1/receipts/{first['id']}", headers=auth).json()["duplicates"] == []


def test_without_tse_it_stays_a_warning(client, auth, png):
    first = upload(client, auth, png).json()[0]
    second = upload(client, auth, png + b"\x00").json()[0]
    assert second["id"] != first["id"] and second["duplicates"] == [first["id"]]
    # a different time tells two purchases apart
    client.patch(f"/api/v1/receipts/{second['id']}", headers=auth, json={"purchased_at": "10:00"})
    assert client.get(f"/api/v1/receipts/{second['id']}", headers=auth).json()["duplicates"] == []
