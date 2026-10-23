import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from haushalt_api import extraction
from haushalt_api.extraction import ClaudeExtractor, ExtractionError, image_tiles, parse_result, receipt_schema


def jpeg(width, height):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_parse_result_converts_to_cents():
    result = parse_result(
        {
            "is_receipt": True,
            "store_name": " Aldi Süd ",
            "purchased_on": "2026-10-20",
            "currency": "eur",
            "total": 3.10,
            "payment_method": "cash",
            "items": [
                {"name": "Butter", "quantity": 2, "unit_price": 1.79, "total": 3.58, "category": "groceries"},
                {"name": "Leergut", "quantity": 1, "unit_price": None, "total": -0.48, "category": "deposit"},
            ],
        }
    )
    assert result.store_name == "Aldi Süd"
    assert result.purchased_on.isoformat() == "2026-10-20"
    assert result.currency == "EUR"
    assert result.total_cents == 310
    assert [(i.name, i.total_cents, i.unit_price_cents) for i in result.items] == [("Butter", 358, 179), ("Leergut", -48, None)]


def test_parse_result_tolerates_missing_values():
    result = parse_result({"purchased_on": "20.10.2026", "total": None, "items": [{"name": "", "total": 1.5}]})
    assert result.purchased_on is None
    assert result.total_cents == 150  # sum of the items
    assert result.items[0].name == "?"


def test_schema_lists_categories_and_is_strict():
    schema = receipt_schema(["groceries", "other"])
    assert schema["additionalProperties"] is False
    item = schema["properties"]["items"]["items"]
    assert item["properties"]["category"]["enum"] == ["groceries", "other"]
    assert set(item["required"]) == set(item["properties"])
    assert set(schema["required"]) == set(schema["properties"])


def test_small_image_is_one_tile():
    assert len(image_tiles(jpeg(800, 1200))) == 1


def test_long_receipt_is_split_into_tiles():
    tiles = image_tiles(jpeg(600, 4000))
    assert 3 <= len(tiles) <= extraction.MAX_TILES
    for tile in tiles:
        image = Image.open(io.BytesIO(base64.b64decode(tile)))
        assert image.height <= image.width * extraction.TILE_RATIO + 2
        assert max(image.size) <= extraction.MAX_EDGE


def test_extremely_long_receipt_is_capped():
    assert len(image_tiles(jpeg(300, 20000))) == extraction.MAX_TILES


def test_broken_image():
    with pytest.raises(ExtractionError):
        image_tiles(b"not an image")


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_client(text, stop_reason="end_turn"):
    response = SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    messages = FakeMessages(response)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_claude_extractor_request_shape():
    answer = json.dumps(
        {"is_receipt": True, "store_name": "dm", "purchased_on": "2026-10-01", "currency": "EUR", "total": 2.95,
         "payment_method": "card", "items": [{"name": "Zahnpasta", "quantity": 1, "unit_price": None, "total": 2.95, "category": "drugstore"}]}
    )
    client, messages = fake_client(answer)
    result = ClaudeExtractor(client=client, model="claude-opus-5-5").extract(jpeg(400, 600), "image/jpeg", ["drugstore"])
    assert result.store_name == "dm" and result.total_cents == 295
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default"
    assert call["output_config"]["format"]["type"] == "json_schema"
    content = call["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[-1]["type"] == "text"


def test_claude_extractor_pdf_is_a_document_block():
    client, messages = fake_client(json.dumps({"is_receipt": False, "store_name": "", "purchased_on": None, "currency": "EUR", "total": None, "payment_method": "unknown", "items": []}))
    result = ClaudeExtractor(client=client).extract(b"%PDF-1.4", "application/pdf", ["other"])
    assert result.is_receipt is False
    assert messages.calls[0]["messages"][0]["content"][0]["type"] == "document"


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_claude_extractor_stop_reasons(stop_reason):
    client, _ = fake_client("{}", stop_reason=stop_reason)
    with pytest.raises(ExtractionError):
        ClaudeExtractor(client=client).extract(jpeg(100, 100), "image/jpeg", ["other"])


def test_claude_extractor_rejects_unknown_type():
    client, _ = fake_client("{}")
    with pytest.raises(ExtractionError):
        ClaudeExtractor(client=client).extract(b"x", "text/plain", ["other"])
