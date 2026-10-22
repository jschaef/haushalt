"""Receipt workflow: store the file, read it, categorize, review, learn.

Categorization order for each line: learned rule for the normalized text,
then the model's suggestion, then the store's default category. When a
person changes the category of a line, the rule is stored or updated, so the
next receipt with that article gets it without asking the model.
"""

import hashlib
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import Category, CategoryRule, Receipt, ReceiptItem, Store
from .extraction import ExtractedReceipt, ExtractionError, Extractor
from .text import normalize, normalize_store

SUFFIX = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "application/pdf": ".pdf"}


def receipt_path(receipt: Receipt):
    return config.RECEIPT_DIR / f"{receipt.id}{SUFFIX.get(receipt.media_type, '.bin')}"


def find_or_create_store(session: Session, name: str) -> Store | None:
    name = name.strip()
    if not name:
        return None
    key = normalize_store(name)
    store = session.scalar(select(Store).where(Store.normalized == key))
    if store is None:
        store = Store(name=name, normalized=key)
        session.add(store)
        session.flush()
    return store


def lookup_rule(session: Session, text: str) -> CategoryRule | None:
    pattern = normalize(text)
    return session.scalar(select(CategoryRule).where(CategoryRule.pattern == pattern)) if pattern else None


def learn(session: Session, text: str, category_id: int) -> None:
    pattern = normalize(text)
    if not pattern:
        return
    rule = session.scalar(select(CategoryRule).where(CategoryRule.pattern == pattern))
    if rule is None:
        session.add(CategoryRule(pattern=pattern, category_id=category_id))
    else:
        rule.category_id = category_id


def apply_extraction(session: Session, receipt: Receipt, result: ExtractedReceipt) -> None:
    categories = {c.key: c.id for c in session.scalars(select(Category))}
    receipt.extraction = result.raw
    receipt.store = find_or_create_store(session, result.store_name)
    receipt.purchased_on = result.purchased_on
    receipt.total_cents = result.total_cents
    receipt.currency = result.currency
    receipt.payment_method = result.payment_method
    receipt.items.clear()
    default_category = receipt.store.default_category_id if receipt.store else None
    for position, item in enumerate(result.items):
        rule = lookup_rule(session, item.name)
        if rule is not None:
            rule.hits += 1
            category_id = rule.category_id
        else:
            category_id = categories.get(item.category_key or "") or default_category
        receipt.items.append(
            ReceiptItem(
                position=position,
                name=item.name,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                total_cents=item.total_cents,
                category_id=category_id,
            )
        )


def ingest(session: Session, extractor: Extractor, user_id: int, data: bytes, media_type: str, file_name: str) -> Receipt:
    """Store one uploaded file as a draft receipt and read it.

    A failed reading keeps the draft with an error, so the file is not lost
    and can be read again later."""
    receipt = Receipt(
        user_id=user_id,
        media_type=media_type,
        file_name=file_name[:256],
        source="pdf" if media_type == "application/pdf" else "photo",
        sha256=hashlib.sha256(data).hexdigest(),
    )
    session.add(receipt)
    session.flush()
    config.RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    receipt_path(receipt).write_bytes(data)
    read(session, extractor, receipt, data)
    session.commit()
    return receipt


def read(session: Session, extractor: Extractor, receipt: Receipt, data: bytes | None = None) -> None:
    if data is None:
        data = receipt_path(receipt).read_bytes()
    category_keys = list(session.scalars(select(Category.key)))
    try:
        result = extractor.extract(data, receipt.media_type, category_keys)
    except ExtractionError as exc:
        receipt.error = str(exc)[:512]
        return
    if not result.is_receipt:
        receipt.error = "not_a_receipt"
        receipt.extraction = result.raw
        return
    receipt.error = ""
    apply_extraction(session, receipt, result)


def duplicates(session: Session, receipt: Receipt) -> list[int]:
    """Other receipts that are probably the same purchase: identical file, or
    same store, same total and a date at most one day apart."""
    found = set(
        session.scalars(select(Receipt.id).where(Receipt.sha256 == receipt.sha256, Receipt.id != receipt.id))
    )
    if receipt.store_id and receipt.purchased_on and receipt.total_cents:
        found.update(
            session.scalars(
                select(Receipt.id).where(
                    Receipt.id != receipt.id,
                    Receipt.store_id == receipt.store_id,
                    Receipt.total_cents == receipt.total_cents,
                    Receipt.purchased_on.between(
                        receipt.purchased_on - timedelta(days=1), receipt.purchased_on + timedelta(days=1)
                    ),
                )
            )
        )
    return sorted(found)


def update(session: Session, receipt: Receipt, changes: dict) -> None:
    """Apply a reviewed version. Category changes of lines are learned."""
    if "store_name" in changes:
        receipt.store = find_or_create_store(session, changes["store_name"] or "")
    if "purchased_on" in changes:
        value = changes["purchased_on"]
        receipt.purchased_on = value if isinstance(value, date) or value is None else date.fromisoformat(value)
    for field in ("total_cents", "currency", "payment_method"):
        if field in changes and changes[field] is not None:
            setattr(receipt, field, changes[field])
    if "items" in changes and changes["items"] is not None:
        old = {item.id: item for item in receipt.items}
        receipt.items.clear()
        for position, data in enumerate(changes["items"]):
            previous = old.get(data.get("id"))
            category_id = data.get("category_id")
            if category_id is not None and (previous is None or previous.category_id != category_id):
                learn(session, data["name"], category_id)
            receipt.items.append(
                ReceiptItem(
                    position=position,
                    name=data["name"],
                    quantity=data.get("quantity", 1.0),
                    unit_price_cents=data.get("unit_price_cents"),
                    total_cents=data["total_cents"],
                    category_id=category_id,
                )
            )
