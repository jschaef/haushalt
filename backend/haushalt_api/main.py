"""HTTP API, prefix /api/v1. The Next.js frontend proxies /api/v1/* here and
adds the bearer token from its httpOnly session cookie."""

import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import config, receipts, stats, utilities_api
from .auth import TokenClaims, create_token, current_claims, current_user, hash_password, revoke, verify_password
from .db import Category, Meter, Receipt, RecurringCost, Store, User, get_session, init_db
from .extraction import get_extractor, sniff
from .ratelimit import login_limiter

logger = logging.getLogger("haushalt_api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


# The OpenAPI pages are off unless asked for: they list every endpoint.
_docs = config.API_DOCS
app = FastAPI(
    title="haushalt-api",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/v1/docs" if _docs else None,
    redoc_url=None,
    openapi_url="/api/v1/openapi.json" if _docs else None,
)
app.include_router(utilities_api.router)
PREFIX = "/api/v1"
LOCALES = ("de", "en")


# --- schemas -----------------------------------------------------------------


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(default="", max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    locale: str


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    locale: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


class CategoryIn(BaseModel):
    key: str = Field(min_length=2, max_length=48, pattern=r"^[a-z0-9_]+$")
    name_de: str = Field(min_length=1, max_length=64)
    name_en: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="variable", pattern=r"^(variable|fixed)$")
    color: str = Field(default="#64748b", pattern=r"^#[0-9a-fA-F]{6}$")
    icon: str = Field(default="tag", max_length=32)


class CategoryOut(CategoryIn):
    id: int


class ItemIn(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=256)
    quantity: float = 1.0
    unit_price_cents: int | None = None
    total_cents: int
    category_id: int | None = None


class ItemOut(ItemIn):
    id: int


class ReceiptPatch(BaseModel):
    store_name: str | None = None
    purchased_on: date | None = None
    total_cents: int | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_method: str | None = None
    items: list[ItemIn] | None = None


class ReceiptOut(BaseModel):
    id: int
    status: str
    source: str
    store_name: str
    purchased_on: date | None
    total_cents: int
    currency: str
    payment_method: str
    file_name: str
    media_type: str
    error: str
    uploaded_by: int
    items: list[ItemOut]
    item_sum_cents: int
    duplicates: list[int] = []


class RecurringIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category_id: int | None = None
    amount_cents: int = Field(gt=0)
    interval_months: int = Field(default=1, ge=1, le=120)
    start_on: date
    end_on: date | None = None
    meter_id: int | None = None


class RecurringOut(RecurringIn):
    id: int
    daily_cents: float


# --- helpers -----------------------------------------------------------------


def receipt_out(receipt: Receipt, session: Session | None = None) -> ReceiptOut:
    items = [
        ItemOut(
            id=i.id,
            name=i.name,
            quantity=i.quantity,
            unit_price_cents=i.unit_price_cents,
            total_cents=i.total_cents,
            category_id=i.category_id,
        )
        for i in receipt.items
    ]
    return ReceiptOut(
        id=receipt.id,
        status=receipt.status,
        source=receipt.source,
        store_name=receipt.store.name if receipt.store else "",
        purchased_on=receipt.purchased_on,
        total_cents=receipt.total_cents,
        currency=receipt.currency,
        payment_method=receipt.payment_method,
        file_name=receipt.file_name,
        media_type=receipt.media_type,
        error=receipt.error,
        uploaded_by=receipt.user_id,
        items=items,
        item_sum_cents=sum(i.total_cents for i in receipt.items),
        duplicates=receipts.duplicates(session, receipt) if session is not None else [],
    )


def get_receipt(session: Session, receipt_id: int) -> Receipt:
    receipt = session.get(Receipt, receipt_id, options=[selectinload(Receipt.items), selectinload(Receipt.store)])
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, display_name=user.display_name, locale=user.locale)


def recurring_out(cost: RecurringCost) -> RecurringOut:
    return RecurringOut(
        id=cost.id,
        name=cost.name,
        category_id=cost.category_id,
        amount_cents=cost.amount_cents,
        interval_months=cost.interval_months,
        start_on=cost.start_on,
        end_on=cost.end_on,
        meter_id=cost.meter_id,
        daily_cents=round(stats.recurring_daily_cents(cost), 2),
    )


def check_meter(session: Session, meter_id: int | None) -> None:
    if meter_id is not None and session.get(Meter, meter_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown meter {meter_id}")


def check_category(session: Session, category_id: int | None) -> None:
    if category_id is not None and session.get(Category, category_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown category {category_id}")


# --- public ------------------------------------------------------------------


@app.get(f"{PREFIX}/health")
def health():
    return {"status": "ok"}


@app.get(f"{PREFIX}/setup")
def setup_state(session: Session = Depends(get_session)):
    """Whether the first user still has to be created (shows signup)."""
    users = session.scalar(select(func.count(User.id))) or 0
    return {"needs_first_user": users == 0, "signup_open": users == 0 or config.ALLOW_SIGNUP}


@app.post(f"{PREFIX}/token")
def login(body: Credentials, request: Request, session: Session = Depends(get_session)):
    key = f"{body.username.lower()}|{request.client.host if request.client else ''}"
    if login_limiter.blocked(key):
        raise HTTPException(status_code=429, detail="Too many failed logins, try again later")
    user = session.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        login_limiter.failure(key)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    login_limiter.reset(key)
    return create_token(user.id)


@app.post(f"{PREFIX}/signup", status_code=201)
def signup(body: NewUser, session: Session = Depends(get_session)):
    """Open while no user exists (or HAUSHALT_ALLOW_SIGNUP is set)."""
    users = session.scalar(select(func.count(User.id))) or 0
    if users and not config.ALLOW_SIGNUP:
        raise HTTPException(status_code=403, detail="Signup is closed, ask a household member")
    user = _create_user(session, body)
    return create_token(user.id)


def _create_user(session: Session, body: NewUser) -> User:
    if session.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status_code=409, detail="Username already taken")
    user = User(
        username=body.username,
        display_name=body.display_name or body.username,
        password_hash=hash_password(body.password),
    )
    session.add(user)
    session.commit()
    return user


# --- session and household ---------------------------------------------------


@app.post(f"{PREFIX}/logout", status_code=204)
def logout(claims: TokenClaims = Depends(current_claims), session: Session = Depends(get_session)):
    revoke(session, claims)


@app.get(f"{PREFIX}/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)


@app.patch(f"{PREFIX}/me", response_model=UserOut)
def update_me(body: UserPatch, user: User = Depends(current_user), session: Session = Depends(get_session)):
    user = session.merge(user)
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.locale is not None:
        if body.locale not in LOCALES:
            raise HTTPException(status_code=422, detail="Unsupported locale")
        user.locale = body.locale
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    session.commit()
    return user_out(user)


@app.get(f"{PREFIX}/users", response_model=list[UserOut])
def list_users(_user: User = Depends(current_user), session: Session = Depends(get_session)):
    return [user_out(u) for u in session.scalars(select(User).order_by(User.username))]


@app.post(f"{PREFIX}/users", response_model=UserOut, status_code=201)
def add_member(body: NewUser, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    return user_out(_create_user(session, body))


# --- categories and stores ---------------------------------------------------


@app.get(f"{PREFIX}/categories", response_model=list[CategoryOut])
def list_categories(_user: User = Depends(current_user), session: Session = Depends(get_session)):
    return [CategoryOut.model_validate(c, from_attributes=True) for c in session.scalars(select(Category).order_by(Category.id))]


@app.post(f"{PREFIX}/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    if session.scalar(select(Category).where(Category.key == body.key)):
        raise HTTPException(status_code=409, detail="Category key exists")
    category = Category(**body.model_dump())
    session.add(category)
    session.commit()
    return CategoryOut.model_validate(category, from_attributes=True)


@app.put(f"{PREFIX}/categories/{{category_id}}", response_model=CategoryOut)
def update_category(
    category_id: int, body: CategoryIn, _user: User = Depends(current_user), session: Session = Depends(get_session)
):
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    clash = session.scalar(select(Category).where(Category.key == body.key, Category.id != category_id))
    if clash:
        raise HTTPException(status_code=409, detail="Category key exists")
    for field, value in body.model_dump().items():
        setattr(category, field, value)
    session.commit()
    return CategoryOut.model_validate(category, from_attributes=True)


@app.get(f"{PREFIX}/stores")
def list_stores(_user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.execute(
        select(Store, func.count(Receipt.id), func.coalesce(func.sum(Receipt.total_cents), 0))
        .outerjoin(Receipt, (Receipt.store_id == Store.id) & (Receipt.status == "confirmed"))
        .group_by(Store.id)
        .order_by(Store.name)
    ).all()
    return [
        {"id": s.id, "name": s.name, "default_category_id": s.default_category_id, "receipts": n, "total_cents": total}
        for s, n, total in rows
    ]


# --- receipts ----------------------------------------------------------------


@app.post(f"{PREFIX}/receipts", response_model=list[ReceiptOut], status_code=201)
async def upload_receipts(
    files: list[UploadFile] = File(...),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """One or more photos/PDFs; every file becomes a draft receipt."""
    created = []
    for upload in files:
        data = await upload.read(config.MAX_UPLOAD_BYTES + 1)
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large: {upload.filename}")
        media_type = sniff(data)
        if media_type is None:
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {upload.filename}")
        receipt = receipts.ingest(session, get_extractor(), user.id, data, media_type, upload.filename or "")
        created.append(receipt_out(get_receipt(session, receipt.id), session))
    return created


@app.get(f"{PREFIX}/receipts", response_model=list[ReceiptOut])
def list_receipts(
    status: str | None = Query(default=None, pattern=r"^(draft|confirmed)$"),
    limit: int = Query(default=200, ge=1, le=1000),
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    query = (
        select(Receipt)
        .options(selectinload(Receipt.items), selectinload(Receipt.store))
        .order_by(Receipt.purchased_on.desc().nulls_first(), Receipt.id.desc())
        .limit(limit)
    )
    if status:
        query = query.where(Receipt.status == status)
    return [receipt_out(r) for r in session.scalars(query)]


@app.get(f"{PREFIX}/receipts/{{receipt_id}}", response_model=ReceiptOut)
def show_receipt(receipt_id: int, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    return receipt_out(get_receipt(session, receipt_id), session)


@app.get(f"{PREFIX}/receipts/{{receipt_id}}/file")
def receipt_file(receipt_id: int, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    receipt = get_receipt(session, receipt_id)
    path = receipts.receipt_path(receipt)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(
        path,
        media_type=receipt.media_type,
        headers={
            "cache-control": "private, max-age=3600",
            "x-content-type-options": "nosniff",
            "content-security-policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox",
        },
    )


@app.patch(f"{PREFIX}/receipts/{{receipt_id}}", response_model=ReceiptOut)
def patch_receipt(
    receipt_id: int, body: ReceiptPatch, _user: User = Depends(current_user), session: Session = Depends(get_session)
):
    receipt = get_receipt(session, receipt_id)
    for item in body.items or []:
        check_category(session, item.category_id)
    changes = body.model_dump(exclude_unset=True)
    receipts.update(session, receipt, changes)
    session.commit()
    return receipt_out(get_receipt(session, receipt_id), session)


@app.post(f"{PREFIX}/receipts/{{receipt_id}}/confirm", response_model=ReceiptOut)
def confirm_receipt(receipt_id: int, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    receipt = get_receipt(session, receipt_id)
    if receipt.purchased_on is None:
        raise HTTPException(status_code=422, detail="Purchase date missing")
    receipt.status = "confirmed"
    session.commit()
    return receipt_out(receipt, session)


@app.post(f"{PREFIX}/receipts/{{receipt_id}}/reread", response_model=ReceiptOut)
def reread_receipt(receipt_id: int, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    receipt = get_receipt(session, receipt_id)
    receipt.status = "draft"
    receipts.read(session, get_extractor(), receipt)
    session.commit()
    return receipt_out(get_receipt(session, receipt_id), session)


@app.delete(f"{PREFIX}/receipts/{{receipt_id}}", status_code=204)
def delete_receipt(receipt_id: int, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    receipt = get_receipt(session, receipt_id)
    receipts.receipt_path(receipt).unlink(missing_ok=True)
    session.delete(receipt)
    session.commit()


# --- recurring costs ---------------------------------------------------------


@app.get(f"{PREFIX}/recurring", response_model=list[RecurringOut])
def list_recurring(_user: User = Depends(current_user), session: Session = Depends(get_session)):
    return [recurring_out(c) for c in session.scalars(select(RecurringCost).order_by(RecurringCost.name))]


@app.post(f"{PREFIX}/recurring", response_model=RecurringOut, status_code=201)
def create_recurring(body: RecurringIn, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    check_category(session, body.category_id)
    check_meter(session, body.meter_id)
    cost = RecurringCost(**body.model_dump())
    session.add(cost)
    session.commit()
    return recurring_out(cost)


@app.put(f"{PREFIX}/recurring/{{cost_id}}", response_model=RecurringOut)
def update_recurring(
    cost_id: int, body: RecurringIn, _user: User = Depends(current_user), session: Session = Depends(get_session)
):
    cost = session.get(RecurringCost, cost_id)
    if cost is None:
        raise HTTPException(status_code=404, detail="Recurring cost not found")
    check_category(session, body.category_id)
    check_meter(session, body.meter_id)
    for field, value in body.model_dump().items():
        setattr(cost, field, value)
    session.commit()
    return recurring_out(cost)


@app.delete(f"{PREFIX}/recurring/{{cost_id}}", status_code=204)
def delete_recurring(cost_id: int, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    cost = session.get(RecurringCost, cost_id)
    if cost is None:
        raise HTTPException(status_code=404, detail="Recurring cost not found")
    session.delete(cost)
    session.commit()


# --- statistics --------------------------------------------------------------


@app.get(f"{PREFIX}/stats/summary")
def stats_summary(
    range: str = Query(default="30d", pattern=r"^(7d|30d|90d|365d|ytd|all)$"),
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    return stats.summary(session, stats.resolve_period(session, range))
