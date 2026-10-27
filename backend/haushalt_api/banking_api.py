"""HTTP API for bank statement import and the review of bookings."""

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import banking, config
from .auth import current_user
from .db import AppState, BankAccount, BankTransaction, Category, MerchantRule, Receipt, RecurringCost, get_session
from .tags_api import resolve_tags
from .text import normalize

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
    account_id: int | None
    receipt_id: int | None
    recurring_id: int | None
    category_id: int | None
    settles_account_id: int | None
    decided_by: str
    one_off: bool
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


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    bank: str = Field(default="", max_length=64)
    iban: str = Field(default="", max_length=42)
    kind: str = Field(default="giro", pattern=r"^(giro|savings)$")
    color: str = Field(default="#64748b", pattern=r"^#[0-9a-fA-F]{6}$")


class AccountOut(BaseModel):
    id: int
    name: str
    bank: str
    iban: str
    card_number: str
    # giro, savings or card (a card statement's account)
    kind: str
    color: str
    bookings: int


def _account_out(session: Session, account: BankAccount) -> AccountOut:
    count = session.scalar(select(func.count(BankTransaction.id)).where(BankTransaction.account_id == account.id)) or 0
    return AccountOut(
        id=account.id,
        name=account.name,
        bank=account.bank,
        iban=account.iban,
        card_number=account.card_number,
        kind="card" if account.card_number else account.kind,
        color=account.color,
        bookings=count,
    )


def _clean_account(session: Session, body: AccountIn, own_id: int | None = None) -> dict:
    iban = banking.normalize_iban(body.iban)
    if iban and not banking.valid_iban(iban):
        raise HTTPException(status_code=422, detail="invalid_iban")
    if iban:
        other = session.scalar(select(BankAccount).where(BankAccount.iban == iban))
        if other is not None and other.id != own_id:
            raise HTTPException(status_code=409, detail="Account with this IBAN exists")
    return {"name": " ".join(body.name.split()), "bank": body.bank.strip(), "iban": iban, "kind": body.kind, "color": body.color}


def _account(session: Session, account_id: int) -> BankAccount:
    account = session.get(BankAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(session: Session = Depends(get_session)):
    return [_account_out(session, a) for a in session.scalars(select(BankAccount).order_by(func.lower(BankAccount.name)))]


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountIn, session: Session = Depends(get_session)):
    account = BankAccount(**_clean_account(session, body))
    session.add(account)
    session.flush()
    # bookings waiting for review may be transfers to this account
    banking.rematch(session)
    return _account_out(session, account)


@router.put("/accounts/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountIn, session: Session = Depends(get_session)):
    account = _account(session, account_id)
    for field, value in _clean_account(session, body, account.id).items():
        setattr(account, field, value)
    banking.rematch(session)
    return _account_out(session, account)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, session: Session = Depends(get_session)):
    """The bookings stay, without an account."""
    session.delete(_account(session, account_id))
    session.commit()


def _transaction(session: Session, tx_id: int) -> BankTransaction:
    tx = session.get(BankTransaction, tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return tx


@router.post("/import")
async def import_statement(
    file: UploadFile = File(...),
    # empty: recognised from the statement (IBAN), else bookings without account
    account_id: int | None = Form(default=None),
    session: Session = Depends(get_session),
):
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    try:
        return banking.import_statement(session, data, account_id)
    except banking.AccountMismatch as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except banking.StatementError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    status: str | None = Query(default=None, pattern="^(" + "|".join(STATUSES) + ")$"),
    # the bank page loads all bookings (a year can hold well over 500)
    limit: int = Query(default=500, ge=1, le=20000),
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
    tx.receipt_id = tx.recurring_id = tx.category_id = tx.settles_account_id = None
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
        banking.learn_recurring(session, tx)
    elif body.status == "counted":
        category = session.get(Category, body.category_id) if body.category_id else None
        if category is None:
            raise HTTPException(status_code=422, detail="category_id required")
        if category.kind == "income" and tx.amount_cents < 0:
            raise HTTPException(status_code=422, detail="income_category_for_payment")
        tx.category_id = body.category_id
        tx.tags = resolve_tags(session, body.tag_ids)
        banking.learn_counterparty(session, tx)
    tx.status = body.status
    # back to review hands the booking to the matching again
    tx.decided_by = "auto" if body.status == "review" else "person"
    session.commit()
    return _out(tx)


class OneOffPatch(BaseModel):
    one_off: bool


@router.put("/transactions/{tx_id}/one-off", response_model=TransactionOut)
def mark_one_off(tx_id: int, body: OneOffPatch, session: Session = Depends(get_session)):
    """Only a person marks one-offs; the matching never changes the flag."""
    tx = _transaction(session, tx_id)
    tx.one_off = body.one_off
    session.commit()
    return _out(tx)


ONE_OFF_KEY = "one_off_threshold_cents"
DEFAULT_ONE_OFF_THRESHOLD = 100_000  # 1,000 euro


class BankSettings(BaseModel):
    # bookings from this amount on are suggested as one-offs; 0 suggests none
    one_off_threshold_cents: int = Field(ge=0, le=100_000_000)


@router.get("/settings", response_model=BankSettings)
def get_settings(session: Session = Depends(get_session)):
    state = session.get(AppState, ONE_OFF_KEY)
    return BankSettings(one_off_threshold_cents=int(state.value) if state else DEFAULT_ONE_OFF_THRESHOLD)


@router.put("/settings", response_model=BankSettings)
def put_settings(body: BankSettings, session: Session = Depends(get_session)):
    state = session.get(AppState, ONE_OFF_KEY) or AppState(key=ONE_OFF_KEY)
    state.value = str(body.one_off_threshold_cents)
    session.add(state)
    session.commit()
    return body


class MerchantIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=64)
    category_id: int


class MerchantOut(BaseModel):
    id: int
    keyword: str
    category_id: int


def _clean_merchant(session: Session, body: MerchantIn, own_id: int | None = None) -> dict:
    keyword = normalize(body.keyword)
    if not keyword:
        raise HTTPException(status_code=422, detail="invalid_keyword")
    category = session.get(Category, body.category_id)
    if category is None:
        raise HTTPException(status_code=422, detail="Unknown category")
    if category.kind == "income":
        raise HTTPException(status_code=422, detail="income_category_for_payment")
    other = session.scalar(select(MerchantRule).where(MerchantRule.keyword == keyword))
    if other is not None and other.id != own_id:
        raise HTTPException(status_code=409, detail="merchant_exists")
    return {"keyword": keyword, "category_id": category.id}


def _merchant(session: Session, merchant_id: int) -> MerchantRule:
    merchant = session.get(MerchantRule, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


def _merchant_out(merchant: MerchantRule) -> MerchantOut:
    return MerchantOut(id=merchant.id, keyword=merchant.keyword, category_id=merchant.category_id)


@router.get("/merchants", response_model=list[MerchantOut])
def list_merchants(session: Session = Depends(get_session)):
    return [_merchant_out(m) for m in session.scalars(select(MerchantRule).order_by(MerchantRule.keyword))]


# a changed list re-matches what the app decided (in the background)
@router.post("/merchants", response_model=MerchantOut, status_code=201)
def create_merchant(body: MerchantIn, background: BackgroundTasks, session: Session = Depends(get_session)):
    merchant = MerchantRule(**_clean_merchant(session, body))
    session.add(merchant)
    session.commit()
    background.add_task(banking.rematch_later)
    return _merchant_out(merchant)


@router.put("/merchants/{merchant_id}", response_model=MerchantOut)
def update_merchant(merchant_id: int, body: MerchantIn, background: BackgroundTasks, session: Session = Depends(get_session)):
    merchant = _merchant(session, merchant_id)
    for field, value in _clean_merchant(session, body, merchant.id).items():
        setattr(merchant, field, value)
    session.commit()
    background.add_task(banking.rematch_later)
    return _merchant_out(merchant)


@router.delete("/merchants/{merchant_id}", status_code=204)
def delete_merchant(merchant_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    session.delete(_merchant(session, merchant_id))
    session.commit()
    background.add_task(banking.rematch_later)


@router.post("/rematch")
def rematch(session: Session = Depends(get_session)):
    return {"matched": banking.rematch(session)}


@router.delete("/transactions/{tx_id}", status_code=204)
def delete_transaction(tx_id: int, session: Session = Depends(get_session)):
    session.delete(_transaction(session, tx_id))
    session.commit()
