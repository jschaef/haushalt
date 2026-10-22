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
            blocks.append({"type": "text", "text": f"The receipt is split into {len(tiles)} overlapping parts, top to bottom."})
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

    def extract(self, data: bytes, media_type: str, category_keys: list[str]) -> ExtractedReceipt:
        import anthropic

        content = content_blocks(data, media_type) + [{"type": "text", "text": PROMPT}]
        try:
            # fallbacks="default": if a safety classifier declines, the API
            # retries on a fallback model inside the same call.
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": receipt_schema(category_keys)},
                },
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
            raise ExtractionError("Receipt too long for one answer")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise ExtractionError("Empty answer from the model")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExtractionError("Answer was not valid JSON") from exc
        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info("receipt read: %s input / %s output tokens", usage.input_tokens, usage.output_tokens)
        return parse_result(raw)


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
    def extract(self, data: bytes, media_type: str, category_keys: list[str]) -> ExtractedReceipt:
        if media_type not in IMAGE_TYPES | {PDF_TYPE}:
            raise ExtractionError(f"Unsupported file type {media_type}")
        raw = json.loads(json.dumps(FAKE_RECEIPT))
        raw["purchased_on"] = date.today().isoformat()
        return parse_result(raw)


_extractor: Extractor | None = None


def get_extractor() -> Extractor:
    global _extractor
    if _extractor is None:
        _extractor = FakeExtractor() if config.EXTRACTOR == "fake" else ClaudeExtractor()
    return _extractor
