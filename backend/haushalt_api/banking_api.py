"""HTTP API for bank statement import and the review of bookings."""

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import banking, config
from .auth import current_user
from .db import BankTransaction, Category, Receipt, RecurringCost, get_session
from .tags_api import resolve_tags

router = APIRouter(prefix="/api/v1/bank", dependencies=[Depends(current_user)])
STATUSES = ("review", "receipt", "fixed", "counted", "ignored")


class TransactionOut(BaseModel):
    id: int
    booked_on: date
    amount_cents: int
    currency: str
    counterparty: str
    iban: str
    purpose: str
    status: str
    receipt_id: int | None
    recurring_id: int | None
    category_id: int | None
    tag_ids: list[int]


class TransactionPatch(BaseModel):
    status: str = Field(pattern="^(" + "|".join(STATUSES) + ")$")
    receipt_id: int | None = None
    recurring_id: int | None = None
    category_id: int | None = None
    # only with status counted (a receipt or recurring cost has its own)
    tag_ids: list[int] = Field(default_factory=list, max_length=20)


def _out(tx: BankTransaction) -> TransactionOut:
    data = {name: getattr(tx, name) for name in TransactionOut.model_fields if name != "tag_ids"}
    return TransactionOut(**data, tag_ids=[tag.id for tag in tx.tags])


def _transaction(session: Session, tx_id: int) -> BankTransaction:
    tx = session.get(BankTransaction, tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return tx


@router.post("/import")
async def import_statement(file: UploadFile = File(...), session: Session = Depends(get_session)):
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    try:
        return banking.import_statement(session, data)
    except banking.StatementError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    status: str | None = Query(default=None, pattern="^(" + "|".join(STATUSES) + ")$"),
    limit: int = Query(default=500, ge=1, le=5000),
    session: Session = Depends(get_session),
):
    query = select(BankTransaction).order_by(BankTransaction.booked_on.desc(), BankTransaction.id.desc()).limit(limit)
    if status:
        query = query.where(BankTransaction.status == status)
    return [_out(tx) for tx in session.scalars(query)]


@router.get("/transactions/{tx_id}/candidates")
def candidates(tx_id: int, session: Session = Depends(get_session)):
    """Receipts that could be the purchase behind this booking."""
    tx = _transaction(session, tx_id)
    if tx.amount_cents >= 0:
        return []
    return [
        {
            "id": r.id,
            "store_name": r.store.name if r.store else "",
            "purchased_on": r.purchased_on.isoformat() if r.purchased_on else None,
            "total_cents": r.total_cents,
            "store_matches": banking.store_in_text(r, tx),
        }
        for r in banking.receipt_candidates(session, tx)
    ]


@router.patch("/transactions/{tx_id}", response_model=TransactionOut)
def decide(tx_id: int, body: TransactionPatch, session: Session = Depends(get_session)):
    """A person's decision; exactly the link the status needs is kept."""
    tx = _transaction(session, tx_id)
    tx.receipt_id = tx.recurring_id = tx.category_id = None
    tx.tags = []
    if body.status == "receipt":
        receipt = session.get(Receipt, body.receipt_id) if body.receipt_id else None
        if receipt is None:
            raise HTTPException(status_code=422, detail="receipt_id required")
        other = session.scalar(
            select(BankTransaction.id).where(BankTransaction.receipt_id == receipt.id, BankTransaction.id != tx.id)
        )
        if other:
            raise HTTPException(status_code=409, detail=f"Receipt already belongs to booking {other}")
        tx.receipt_id = receipt.id
    elif body.status == "fixed":
        if not body.recurring_id or session.get(RecurringCost, body.recurring_id) is None:
            raise HTTPException(status_code=422, detail="recurring_id required")
        tx.recurring_id = body.recurring_id
    elif body.status == "counted":
        if not body.category_id or session.get(Category, body.category_id) is None:
            raise HTTPException(status_code=422, detail="category_id required")
        tx.category_id = body.category_id
        tx.tags = resolve_tags(session, body.tag_ids)
        banking.learn_counterparty(session, tx)
    tx.status = body.status
    session.commit()
    return _out(tx)


@router.post("/rematch")
def rematch(session: Session = Depends(get_session)):
    return {"matched": banking.rematch(session)}


@router.delete("/transactions/{tx_id}", status_code=204)
def delete_transaction(tx_id: int, session: Session = Depends(get_session)):
    session.delete(_transaction(session, tx_id))
    session.commit()
