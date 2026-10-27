"""HTTP API, prefix /api/v1. The Next.js frontend proxies /api/v1/* here and
adds the bearer token from its httpOnly session cookie."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import banking, banking_api, config, operator_api, receipts, smartmeter, smartmeter_api, stats, tags_api, tenancy, utilities_api
from .auth import (
    TokenClaims,
    admin_user,
    create_token,
    current_claims,
    current_user,
    hash_password,
    revoke,
    session_user,
    verify_password,
)
from .passwords import MAX_LENGTH, one_time_password, problems
from .db import (
    BankTransaction,
    Category,
    Household,
    Meter,
    Receipt,
    RecurringCost,
    SessionLocal,
    Store,
    User,
    create_household,
    get_session,
    get_setting,
    init_db,
    set_setting,
)
from .extraction import get_extractor, sniff
from .ratelimit import login_limiter
from .tags_api import resolve_tags

logger = logging.getLogger("haushalt_api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    poller = asyncio.create_task(smartmeter.poll_forever()) if config.POLL_MINUTES > 0 else None
    housekeeping = asyncio.create_task(daily_housekeeping())
    yield
    housekeeping.cancel()
    if poller:
        poller.cancel()


async def daily_housekeeping() -> None:
    """Once at start and then daily: delete receipt files past retention."""
    while True:
        try:
            with tenancy.unscoped(SessionLocal()) as session:
                expired = await asyncio.to_thread(receipts.expire_files, session)
            if expired:
                logger.info("deleted %s receipt files after the retention period", expired)
        except Exception:  # keep the loop alive; the error is logged
            logger.exception("housekeeping failed")
        await asyncio.sleep(24 * 3600)


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
app.include_router(smartmeter_api.router)
app.include_router(smartmeter_api.ingest_router)
app.include_router(utilities_api.router)
app.include_router(banking_api.router)
app.include_router(tags_api.router)
app.include_router(operator_api.router)
PREFIX = "/api/v1"
LOCALES = ("de", "en")


# --- schemas -----------------------------------------------------------------


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


USERNAME = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")


class NewUser(BaseModel):
    username: str = USERNAME
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(default="", max_length=128)


class NewMember(BaseModel):
    """Added by an admin; the member gets a one-time password."""

    username: str = USERNAME
    display_name: str = Field(default="", max_length=128)
    is_admin: bool = False


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    locale: str
    is_admin: bool
    disabled: bool
    must_change_password: bool
    is_operator: bool = False


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    locale: str | None = None


class MemberPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    is_admin: bool | None = None
    disabled: bool | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class OneTimePassword(BaseModel):
    user: "UserOut"
    one_time_password: str


class CategoryIn(BaseModel):
    key: str = Field(min_length=2, max_length=48, pattern=r"^[a-z0-9_]+$")
    name_de: str = Field(min_length=1, max_length=64)
    name_en: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="variable", pattern=r"^(variable|fixed|income)$")
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
    file_deleted: bool = False


class RecurringIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category_id: int | None = None
    amount_cents: int = Field(gt=0)
    interval_months: int = Field(default=1, ge=1, le=120)
    start_on: date
    end_on: date | None = None
    meter_id: int | None = None
    # None keeps the tags (an update that does not know them must not drop them)
    tag_ids: list[int] | None = Field(default=None, max_length=20)


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
        file_deleted=receipt.file_deleted_at is not None,
        duplicates=receipts.duplicates(session, receipt) if session is not None else [],
    )


def get_receipt(session: Session, receipt_id: int) -> Receipt:
    receipt = session.get(Receipt, receipt_id, options=[selectinload(Receipt.items), selectinload(Receipt.store)])
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        locale=user.locale,
        is_admin=user.is_admin,
        disabled=user.disabled,
        must_change_password=user.must_change_password,
        is_operator=user.is_operator,
    )


def check_password(password: str, username: str, display_name: str = "") -> None:
    found = problems(password, username=username, display_name=display_name)
    if found:
        # codes, the UI explains them in the user's language
        raise HTTPException(status_code=422, detail={"code": "weak_password", "reasons": found, "max_length": MAX_LENGTH})


def token_out(user: User) -> dict:
    return {**create_token(user), "must_change_password": user.must_change_password, "is_operator": user.is_operator}


def end_sessions(user: User) -> None:
    user.token_version += 1


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
        tag_ids=[tag.id for tag in cost.tags],
        daily_cents=round(stats.recurring_daily_cents(cost), 2),
    )


def reopen_bookings(session: Session, condition) -> None:
    """Bank bookings linked to something that is deleted go back to review,
    otherwise they would count nowhere."""
    for tx in session.scalars(select(BankTransaction).where(condition)):
        tx.status, tx.receipt_id, tx.recurring_id = "review", None, None


def check_meter(session: Session, meter_id: int | None) -> None:
    if meter_id is not None and session.get(Meter, meter_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown meter {meter_id}")


def check_category(session: Session, category_id: int | None) -> None:
    if category_id is not None and session.get(Category, category_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown category {category_id}")


# the household the first account sets up (Jochen, 2026-10-27)
FIRST_HOUSEHOLD = "Mein Haushalt"


# --- public ------------------------------------------------------------------


@app.get(f"{PREFIX}/health")
def health():
    return {"status": "ok"}


@app.get(f"{PREFIX}/setup")
def setup_state(session: Session = Depends(get_session)):
    """Whether the first user still has to be created (shows signup)."""
    # household members; the operator alone sets up no household
    users = session.scalar(tenancy.everywhere(select(func.count(User.id)).where(User.is_operator.is_(False)))) or 0
    return {"needs_first_user": users == 0, "signup_open": users == 0 or config.ALLOW_SIGNUP}


@app.post(f"{PREFIX}/token")
def login(body: Credentials, request: Request, session: Session = Depends(get_session)):
    key = f"{body.username.lower()}|{request.client.host if request.client else ''}"
    if login_limiter.blocked(key):
        raise HTTPException(status_code=429, detail="Too many failed logins, try again later")
    # the username names the household: look in all of them
    user = session.scalar(tenancy.everywhere(select(User).where(User.username == body.username)))
    if user is None or not verify_password(body.password, user.password_hash):
        login_limiter.failure(key)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    login_limiter.reset(key)
    if user.disabled:
        raise HTTPException(status_code=403, detail="account_disabled")
    return token_out(user)


@app.post(f"{PREFIX}/signup", status_code=201)
def signup(body: NewUser, session: Session = Depends(get_session)):
    """Open while no user exists (or HAUSHALT_ALLOW_SIGNUP is set). The first
    account sets up the first household and runs it; later ones (with
    HAUSHALT_ALLOW_SIGNUP) join that household."""
    # household members; the operator alone sets up no household
    users = session.scalar(tenancy.everywhere(select(func.count(User.id)).where(User.is_operator.is_(False)))) or 0
    if users and not config.ALLOW_SIGNUP:
        raise HTTPException(status_code=403, detail="Signup is closed, ask a household member")
    check_password(body.password, body.username, body.display_name)
    household = session.scalar(select(Household).order_by(Household.id).limit(1))
    if household is None:
        household = create_household(session, FIRST_HOUSEHOLD)
    tenancy.bind(session, household.id)
    user = _create_user(session, body.username, body.display_name, body.password, is_admin=users == 0)
    return token_out(user)


def _create_user(
    session: Session, username: str, display_name: str, password: str, *, is_admin: bool = False, must_change: bool = False
) -> User:
    # usernames are unique in all households (the login names none)
    if session.scalar(tenancy.everywhere(select(User).where(User.username == username))):
        raise HTTPException(status_code=409, detail="Username already taken")
    user = User(
        household_id=tenancy.current(session),
        username=username,
        display_name=display_name or username,
        password_hash=hash_password(password),
        is_admin=is_admin,
        must_change_password=must_change,
    )
    session.add(user)
    session.commit()
    return user


# --- session and household ---------------------------------------------------


@app.post(f"{PREFIX}/logout", status_code=204)
def logout(claims: TokenClaims = Depends(current_claims), session: Session = Depends(get_session)):
    revoke(session, claims)


@app.get(f"{PREFIX}/me", response_model=UserOut)
def me(user: User = Depends(session_user)):
    return user_out(user)


@app.post(f"{PREFIX}/me/password")
def change_password(body: PasswordChange, user: User = Depends(session_user), session: Session = Depends(get_session)):
    """Also the way out of a one-time password. Ends all other sessions and
    returns a new token for this one."""
    user = session.merge(user)
    key = f"password|{user.id}"
    if login_limiter.blocked(key):
        raise HTTPException(status_code=429, detail="Too many failed attempts, try again later")
    if not verify_password(body.current_password, user.password_hash):
        login_limiter.failure(key)
        raise HTTPException(status_code=403, detail="wrong_current_password")
    login_limiter.reset(key)
    if body.new_password == body.current_password:
        raise HTTPException(status_code=422, detail={"code": "weak_password", "reasons": ["unchanged"], "max_length": MAX_LENGTH})
    check_password(body.new_password, user.username, user.display_name)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    end_sessions(user)
    session.commit()
    return token_out(user)


@app.patch(f"{PREFIX}/me", response_model=UserOut)
def update_me(body: UserPatch, user: User = Depends(current_user), session: Session = Depends(get_session)):
    user = session.merge(user)
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.locale is not None:
        if body.locale not in LOCALES:
            raise HTTPException(status_code=422, detail="Unsupported locale")
        user.locale = body.locale
    session.commit()
    return user_out(user)


class HouseholdIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class HouseholdOut(HouseholdIn):
    id: int


@app.get(f"{PREFIX}/household", response_model=HouseholdOut)
def get_household(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """The household of the logged-in member."""
    household = session.get(Household, user.household_id) if user.household_id else None
    if household is None:
        raise HTTPException(status_code=404, detail="No household")
    return HouseholdOut(id=household.id, name=household.name)


@app.put(f"{PREFIX}/household", response_model=HouseholdOut)
def rename_household(body: HouseholdIn, admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    household = session.get(Household, admin.household_id) if admin.household_id else None
    if household is None:
        raise HTTPException(status_code=404, detail="No household")
    household.name = " ".join(body.name.split())
    session.commit()
    return HouseholdOut(id=household.id, name=household.name)


@app.get(f"{PREFIX}/users", response_model=list[UserOut])
def list_users(_user: User = Depends(current_user), session: Session = Depends(get_session)):
    return [user_out(u) for u in session.scalars(select(User).order_by(User.username))]


@app.post(f"{PREFIX}/users", response_model=OneTimePassword, status_code=201)
def add_member(body: NewMember, _admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    """The admin passes the one-time password on; the member replaces it at
    the first login, so nobody but the member knows the final password."""
    password = one_time_password()
    user = _create_user(session, body.username, body.display_name, password, is_admin=body.is_admin, must_change=True)
    return OneTimePassword(user=user_out(user), one_time_password=password)


def _member(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Unknown member")
    return user


@app.post(f"{PREFIX}/users/{{user_id}}/reset-password", response_model=OneTimePassword)
def reset_password(user_id: int, admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    if user_id == admin.id:
        raise HTTPException(status_code=409, detail="Change your own password in your profile")
    user = _member(session, user_id)
    password = one_time_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    end_sessions(user)
    session.commit()
    return OneTimePassword(user=user_out(user), one_time_password=password)


@app.patch(f"{PREFIX}/users/{{user_id}}", response_model=UserOut)
def update_member(user_id: int, body: MemberPatch, admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    user = _member(session, user_id)
    if user.id == admin.id and (body.is_admin is False or body.disabled):
        # the household must not lock itself out
        raise HTTPException(status_code=409, detail="You cannot remove your own admin role or disable yourself")
    if body.display_name is not None:
        user.display_name = body.display_name or user.username
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.disabled is not None and body.disabled != user.disabled:
        user.disabled = body.disabled
        end_sessions(user)
    session.commit()
    return user_out(user)


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
    if receipt.file_deleted_at is not None:
        raise HTTPException(status_code=410, detail="File deleted after the retention period")
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
def confirm_receipt(
    receipt_id: int, background: BackgroundTasks, _user: User = Depends(current_user), session: Session = Depends(get_session)
):
    receipt = get_receipt(session, receipt_id)
    if receipt.purchased_on is None:
        raise HTTPException(status_code=422, detail="Purchase date missing")
    receipt.status = "confirmed"
    session.commit()
    # a booking the app counted by its merchant (a supermarket) belongs to
    # this receipt now, else the purchase would count twice
    background.add_task(banking.rematch_later, tenancy.current(session))
    return receipt_out(receipt, session)


@app.post(f"{PREFIX}/receipts/{{receipt_id}}/reread", response_model=ReceiptOut)
def reread_receipt(receipt_id: int, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    receipt = get_receipt(session, receipt_id)
    if receipt.file_deleted_at is not None:
        raise HTTPException(status_code=422, detail="File deleted after the retention period")
    receipt.status = "draft"
    receipts.read(session, get_extractor(), receipt)
    session.commit()
    return receipt_out(get_receipt(session, receipt_id), session)


@app.delete(f"{PREFIX}/receipts/{{receipt_id}}", status_code=204)
def delete_receipt(receipt_id: int, _user: User = Depends(current_user), session: Session = Depends(get_session)):
    receipt = get_receipt(session, receipt_id)
    receipts.receipt_path(receipt).unlink(missing_ok=True)
    reopen_bookings(session, BankTransaction.receipt_id == receipt.id)
    session.delete(receipt)
    session.commit()


# --- recurring costs ---------------------------------------------------------


@app.get(f"{PREFIX}/recurring", response_model=list[RecurringOut])
def list_recurring(_user: User = Depends(current_user), session: Session = Depends(get_session)):
    return [recurring_out(c) for c in session.scalars(select(RecurringCost).order_by(RecurringCost.name))]


@app.post(f"{PREFIX}/recurring", response_model=RecurringOut, status_code=201)
def create_recurring(
    body: RecurringIn, background: BackgroundTasks, _user: User = Depends(current_user), session: Session = Depends(get_session)
):
    check_category(session, body.category_id)
    check_meter(session, body.meter_id)
    cost = RecurringCost(**body.model_dump(exclude={"tag_ids"}), tags=resolve_tags(session, body.tag_ids or []))
    session.add(cost)
    session.commit()
    # bookings the app decided by itself may belong to this cost now
    background.add_task(banking.rematch_later, tenancy.current(session))
    return recurring_out(cost)


@app.put(f"{PREFIX}/recurring/{{cost_id}}", response_model=RecurringOut)
def update_recurring(
    cost_id: int,
    body: RecurringIn,
    background: BackgroundTasks,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    cost = session.get(RecurringCost, cost_id)
    if cost is None:
        raise HTTPException(status_code=404, detail="Recurring cost not found")
    check_category(session, body.category_id)
    check_meter(session, body.meter_id)
    for field, value in body.model_dump(exclude={"tag_ids"}).items():
        setattr(cost, field, value)
    if body.tag_ids is not None:
        cost.tags = resolve_tags(session, body.tag_ids)
    session.commit()
    background.add_task(banking.rematch_later, tenancy.current(session))
    return recurring_out(cost)


@app.delete(f"{PREFIX}/recurring/{{cost_id}}", status_code=204)
def delete_recurring(
    cost_id: int, background: BackgroundTasks, _user: User = Depends(current_user), session: Session = Depends(get_session)
):
    cost = session.get(RecurringCost, cost_id)
    if cost is None:
        raise HTTPException(status_code=404, detail="Recurring cost not found")
    reopen_bookings(session, BankTransaction.recurring_id == cost.id)
    session.delete(cost)
    session.commit()
    background.add_task(banking.rematch_later, tenancy.current(session))


# --- statistics --------------------------------------------------------------


@app.get(f"{PREFIX}/stats/summary")
def stats_summary(
    range: str = Query(default="30d", pattern=r"^(7d|30d|90d|365d|ytd|all|custom)$"),
    # range=custom: from start to end (today if left out)
    start: date | None = None,
    end: date | None = None,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    if range != "custom":
        return stats.summary(session, stats.resolve_period(session, range))
    if start is None:
        raise HTTPException(status_code=422, detail="start_required")
    try:
        return stats.summary(session, stats.custom_period(start, end))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class ResetDate(BaseModel):
    # None lifts the reset: the dashboard counts everything again
    since: date | None = None


@app.get(f"{PREFIX}/stats/since", response_model=ResetDate)
def get_reset_date(_user: User = Depends(current_user), session: Session = Depends(get_session)):
    return ResetDate(since=stats.reset_date(session))


@app.put(f"{PREFIX}/stats/since", response_model=ResetDate)
def put_reset_date(body: ResetDate, _admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    """Household-wide, so only admins move it."""
    if body.since is not None and body.since > date.today():
        raise HTTPException(status_code=422, detail="reset_in_future")
    set_setting(session, stats.SINCE_KEY, body.since.isoformat() if body.since else "")
    session.commit()
    return body
