"""Reading receipts: photo or PDF in, structured receipt out.

ClaudeExtractor sends the file to the Anthropic Messages API with a JSON
schema (structured outputs), so the answer always parses. FakeExtractor
returns a fixed receipt and is used by the tests and the e2e server.
"""

import base64
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from PIL import Image, ImageOps

from . import config

logger = logging.getLogger("haushalt_api")

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
PDF_TYPE = "application/pdf"

# The API scales images down to about 1568 px on the long edge. A long
# receipt would become unreadable, so tall images are cut into overlapping
# tiles of at most 1:2 that are sent together in one request.
TILE_RATIO = 2.0
TILE_OVERLAP = 0.08
MAX_TILES = 8
MAX_EDGE = 1568

# Decompression bombs: a phone photo has about 12-50 megapixels.
Image.MAX_IMAGE_PIXELS = 80_000_000

_MAGIC = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", PDF_TYPE),
]


def sniff(data: bytes) -> str | None:
    """Media type from the file's first bytes; the client's claim is not trusted."""
    for magic, media_type in _MAGIC:
        if data.startswith(magic):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class ExtractionError(Exception):
    pass


@dataclass
class ExtractedItem:
    name: str
    total_cents: int
    quantity: float = 1.0
    unit_price_cents: int | None = None
    category_key: str | None = None


@dataclass
class ExtractedReceipt:
    is_receipt: bool
    store_name: str = ""
    purchased_on: date | None = None
    total_cents: int = 0
    currency: str = "EUR"
    payment_method: str = ""
    items: list[ExtractedItem] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class Extractor(Protocol):
    def extract(self, data: bytes, media_type: str, category_keys: list[str]) -> ExtractedReceipt: ...

    def read_meter(self, data: bytes, media_type: str) -> dict: ...

    def read_bill(self, data: bytes, media_type: str) -> dict: ...


def _cents(value) -> int | None:
    if value is None:
        return None
    return int(round(float(value) * 100))


def parse_result(raw: dict) -> ExtractedReceipt:
    """Turn the model's JSON (amounts in currency units) into cents."""
    purchased_on = None
    if raw.get("purchased_on"):
        try:
            purchased_on = date.fromisoformat(raw["purchased_on"])
        except ValueError:
            purchased_on = None
    items = [
        ExtractedItem(
            name=str(item.get("name", "")).strip()[:256] or "?",
            total_cents=_cents(item.get("total")) or 0,
            quantity=float(item.get("quantity") or 1),
            unit_price_cents=_cents(item.get("unit_price")),
            category_key=item.get("category"),
        )
        for item in raw.get("items") or []
    ]
    total = _cents(raw.get("total"))
    if total is None:
        total = sum(item.total_cents for item in items)
    return ExtractedReceipt(
        is_receipt=bool(raw.get("is_receipt", True)),
        store_name=str(raw.get("store_name") or "").strip()[:128],
        purchased_on=purchased_on,
        total_cents=total,
        currency=(raw.get("currency") or "EUR").upper()[:3],
        payment_method=str(raw.get("payment_method") or "")[:32],
        items=items,
        raw=raw,
    )


def receipt_schema(category_keys: list[str]) -> dict:
    nullable_number = {"type": ["number", "null"]}
    return {
        "type": "object",
        "properties": {
            "is_receipt": {"type": "boolean"},
            "store_name": {"type": "string"},
            "purchased_on": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "currency": {"type": "string"},
            "total": nullable_number,
            "payment_method": {"type": "string", "enum": ["cash", "card", "other", "unknown"]},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit_price": nullable_number,
                        "total": {"type": "number"},
                        "category": {"type": "string", "enum": category_keys},
                    },
                    "required": ["name", "quantity", "unit_price", "total", "category"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["is_receipt", "store_name", "purchased_on", "currency", "total", "payment_method", "items"],
        "additionalProperties": False,
    }


PROMPT = """Read this shopping receipt (usually German) and return its content as JSON.

- store_name: the shop or chain as a person would name it (e.g. "REWE", "Aldi Süd", "dm").
- purchased_on: purchase date as YYYY-MM-DD, null if not printed.
- items: one entry per article line in receipt order. Use the article text as printed,
  expanded only where an abbreviation is obvious. quantity and unit_price come from lines
  like "2 x 1,29"; total is the line amount. Discounts, coupons and returned deposit
  (Pfand, Leergut) are their own items with a negative total. Do not list subtotals,
  tax lines, payment lines or change.
- total: the amount paid. The item totals should add up to it.
- category: the best fitting key; deposit lines use "deposit" if that key exists.
- Amounts are plain numbers in the receipt currency (1,29 € -> 1.29).
- If the image is not a receipt or invoice, set is_receipt to false and leave items empty."""


def _encode_jpeg(image: Image.Image) -> str:
    if max(image.size) > MAX_EDGE:
        image = image.copy()
        image.thumbnail((MAX_EDGE, MAX_EDGE))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=88)
    return base64.standard_b64encode(buffer.getvalue()).decode()


def image_tiles(data: bytes) -> list[str]:
    """base64 JPEG tiles of an image, top to bottom."""
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    except Image.DecompressionBombError as exc:
        raise ExtractionError("Image too large") from exc
    except Exception as exc:  # Pillow raises many types for broken files
        raise ExtractionError(f"Unreadable image: {exc}") from exc
    width, height = image.size
    tile_height = int(width * TILE_RATIO)
    if height <= tile_height * 1.15:
        return [_encode_jpeg(image)]
    step = int(tile_height * (1 - TILE_OVERLAP))
    count = min(MAX_TILES, -(-(height - tile_height) // step) + 1)
    if count == MAX_TILES:  # very long receipt: stretch the tiles instead
        tile_height = int(height / (MAX_TILES * (1 - TILE_OVERLAP) + TILE_OVERLAP))
        step = int(tile_height * (1 - TILE_OVERLAP))
    tiles = []
    for index in range(count):
        top = min(index * step, height - tile_height)
        tiles.append(_encode_jpeg(image.crop((0, top, width, top + tile_height))))
    return tiles


def content_blocks(data: bytes, media_type: str) -> list[dict]:
    if media_type == PDF_TYPE:
        encoded = base64.standard_b64encode(data).decode()
        return [{"type": "document", "source": {"type": "base64", "media_type": PDF_TYPE, "data": encoded}}]
    if media_type in IMAGE_TYPES:
        tiles = image_tiles(data)
        blocks: list[dict] = []
        if len(tiles) > 1:
            blocks.append({"type": "text", "text": f"The image is split into {len(tiles)} overlapping parts, top to bottom."})
        for tile in tiles:
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": tile}})
        return blocks
    raise ExtractionError(f"Unsupported file type {media_type}")


class ClaudeExtractor:
    def __init__(self, client=None, model: str | None = None, effort: str | None = None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.model = model or config.RECEIPT_MODEL
        self.effort = effort or config.RECEIPT_EFFORT

    def _ask(self, data: bytes, media_type: str, prompt: str, schema: dict, what: str) -> dict:
        """One structured-output request about one file; the parsed JSON answer."""
        import anthropic

        content = content_blocks(data, media_type) + [{"type": "text", "text": prompt}]
        try:
            # fallbacks="default": if a safety classifier declines, the API
            # retries on a fallback model inside the same call.
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.RateLimitError as exc:
            raise ExtractionError("Rate limited by the Anthropic API, try again later") from exc
        except anthropic.APIStatusError as exc:
            raise ExtractionError(f"Anthropic API error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise ExtractionError("Anthropic API not reachable") from exc
        if response.stop_reason == "refusal":
            raise ExtractionError("The model declined to read this file")
        if response.stop_reason == "max_tokens":
            raise ExtractionError("File too long for one answer")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise ExtractionError("Empty answer from the model")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExtractionError("Answer was not valid JSON") from exc
        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info("%s read: %s input / %s output tokens", what, usage.input_tokens, usage.output_tokens)
        return raw

    def extract(self, data: bytes, media_type: str, category_keys: list[str]) -> ExtractedReceipt:
        return parse_result(self._ask(data, media_type, PROMPT, receipt_schema(category_keys), "receipt"))

    def read_meter(self, data: bytes, media_type: str) -> dict:
        return parse_meter(self._ask(data, media_type, METER_PROMPT, METER_SCHEMA, "meter"))

    def read_bill(self, data: bytes, media_type: str) -> dict:
        return parse_bill(self._ask(data, media_type, BILL_PROMPT, BILL_SCHEMA, "bill"))


FAKE_RECEIPT = {
    "is_receipt": True,
    "store_name": "REWE",
    "purchased_on": None,  # today, filled in by FakeExtractor
    "currency": "EUR",
    "total": 12.43,
    "payment_method": "card",
    "items": [
        {"name": "JA! Frischmilch 3,5% 1L", "quantity": 2, "unit_price": 1.09, "total": 2.18, "category": "groceries"},
        {"name": "Bio Bananen", "quantity": 1, "unit_price": None, "total": 1.99, "category": "groceries"},
        {"name": "Mineralwasser 6x1,5L", "quantity": 1, "unit_price": None, "total": 3.54, "category": "drinks"},
        {"name": "Pfand", "quantity": 1, "unit_price": None, "total": 1.50, "category": "deposit"},
        {"name": "Spülmittel", "quantity": 1, "unit_price": None, "total": 3.22, "category": "household"},
    ],
}


class FakeExtractor:
    @staticmethod
    def _check(media_type: str) -> None:
        if media_type not in IMAGE_TYPES | {PDF_TYPE}:
            raise ExtractionError(f"Unsupported file type {media_type}")

    def read_meter(self, data: bytes, media_type: str) -> dict:
        self._check(media_type)
        return parse_meter(FAKE_METER)

    def read_bill(self, data: bytes, media_type: str) -> dict:
        self._check(media_type)
        return parse_bill(FAKE_BILL)

    def extract(self, data: bytes, media_type: str, category_keys: list[str]) -> ExtractedReceipt:
        if media_type not in IMAGE_TYPES | {PDF_TYPE}:
            raise ExtractionError(f"Unsupported file type {media_type}")
        raw = json.loads(json.dumps(FAKE_RECEIPT))
        raw["purchased_on"] = date.today().isoformat()
        return parse_result(raw)


# --- utility meters and bills ---------------------------------------------

UTILITY_KINDS = ["electricity", "gas", "water", "heat", "other"]

METER_PROMPT = """This photo shows a utility meter (electricity, gas, water or heat), usually German.
Return the reading as JSON.
- value: the number on the main register as a decimal number. Digits after the decimal
  separator are often red or in a red frame; include them as decimals. Ignore other
  numbers (meter number, year of calibration, constants like "imp/kWh").
- unit: the unit printed next to the register (kWh, m3, MWh, ...).
- meter_number: the serial number printed on the meter (often "Nr." or a barcode
  number), empty string if not readable.
- kind: electricity for kWh meters, gas for gas meters (m3, often "Gas" or "G4"), water
  for water meters (m3), heat for heat meters.
- If the photo is not a meter or the register is not readable, set is_meter to false."""

METER_SCHEMA = {
    "type": "object",
    "properties": {
        "is_meter": {"type": "boolean"},
        "kind": {"type": "string", "enum": UTILITY_KINDS},
        "value": {"type": ["number", "null"]},
        "unit": {"type": "string"},
        "meter_number": {"type": "string"},
    },
    "required": ["is_meter", "kind", "value", "unit", "meter_number"],
    "additionalProperties": False,
}

BILL_PROMPT = """This is an annual utility bill (Jahresabrechnung) for electricity, gas, water
or heat, usually German. Return its key figures as JSON. Amounts are gross (incl. VAT),
plain numbers in EUR.
- period_start, period_end: billing period as YYYY-MM-DD.
- consumption and unit: total consumption in the period (kWh or m3).
- total_cost: gross total for the period.
- paid: sum of instalments (Abschlaege) paid in the period.
- balance: paid minus total_cost (positive = credit/Guthaben, negative = Nachzahlung).
- unit_price_ct: gross energy/working price in cent per unit (Arbeitspreis), null if not stated.
- base_fee_monthly: gross base fee per month (Grundpreis), null if not stated.
- new_instalment: the new monthly instalment from now on, null if not stated.
- meter_number: the meter number on the bill, empty string if none.
- provider: the supplier's name.
If the document is not a utility bill, set is_bill to false."""

BILL_SCHEMA = {
    "type": "object",
    "properties": {
        "is_bill": {"type": "boolean"},
        "kind": {"type": "string", "enum": UTILITY_KINDS},
        "provider": {"type": "string"},
        "meter_number": {"type": "string"},
        "period_start": {"type": ["string", "null"]},
        "period_end": {"type": ["string", "null"]},
        "consumption": {"type": ["number", "null"]},
        "unit": {"type": "string"},
        "total_cost": {"type": ["number", "null"]},
        "paid": {"type": ["number", "null"]},
        "balance": {"type": ["number", "null"]},
        "unit_price_ct": {"type": ["number", "null"]},
        "base_fee_monthly": {"type": ["number", "null"]},
        "new_instalment": {"type": ["number", "null"]},
    },
    "required": [
        "is_bill", "kind", "provider", "meter_number", "period_start", "period_end", "consumption", "unit",
        "total_cost", "paid", "balance", "unit_price_ct", "base_fee_monthly", "new_instalment",
    ],
    "additionalProperties": False,
}


def _iso(value) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _unit(text: str) -> str:
    value = (text or "").strip().replace("³", "3").replace(" ", "")
    return {"m3": "m³", "kwh": "kWh", "mwh": "MWh"}.get(value.lower(), value[:16])


def parse_meter(raw: dict) -> dict:
    value = raw.get("value")
    return {
        "is_meter": bool(raw.get("is_meter")) and value is not None,
        "kind": raw.get("kind") if raw.get("kind") in UTILITY_KINDS else "other",
        "value": float(value) if value is not None else None,
        "unit": _unit(raw.get("unit", "")),
        "meter_number": str(raw.get("meter_number") or "").strip()[:64],
    }


def parse_bill(raw: dict) -> dict:
    total = _cents(raw.get("total_cost"))
    paid = _cents(raw.get("paid"))
    balance = _cents(raw.get("balance"))
    if balance is None and total is not None and paid is not None:
        balance = paid - total
    return {
        "is_bill": bool(raw.get("is_bill")),
        "kind": raw.get("kind") if raw.get("kind") in UTILITY_KINDS else "other",
        "provider": str(raw.get("provider") or "").strip()[:128],
        "meter_number": str(raw.get("meter_number") or "").strip()[:64],
        "period_start": _iso(raw.get("period_start")),
        "period_end": _iso(raw.get("period_end")),
        "consumption": float(raw["consumption"]) if raw.get("consumption") is not None else None,
        "unit": _unit(raw.get("unit", "")),
        "total_cents": total,
        "paid_cents": paid,
        "balance_cents": balance,
        "unit_price_ct": float(raw["unit_price_ct"]) if raw.get("unit_price_ct") is not None else None,
        "base_fee_monthly_cents": _cents(raw.get("base_fee_monthly")),
        "new_instalment_cents": _cents(raw.get("new_instalment")),
    }


FAKE_METER = {"is_meter": True, "kind": "electricity", "value": 12345.6, "unit": "kWh", "meter_number": "1ESY1160123456"}

FAKE_BILL = {
    "is_bill": True, "kind": "electricity", "provider": "Stadtwerke Beispiel", "meter_number": "1ESY1160123456",
    "period_start": "2025-01-01", "period_end": "2025-12-31", "consumption": 2400, "unit": "kWh",
    "total_cost": 960.0, "paid": 900.0, "balance": -60.0, "unit_price_ct": 32.5, "base_fee_monthly": 15.0,
    "new_instalment": 85.0,
}


_extractor: Extractor | None = None


def get_extractor() -> Extractor:
    global _extractor
    if _extractor is None:
        _extractor = FakeExtractor() if config.EXTRACTOR == "fake" else ClaudeExtractor()
    return _extractor
