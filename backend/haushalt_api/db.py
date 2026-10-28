"""Database models (SQLAlchemy 2). Money is stored as integer cents.

Several households share one installation; every row of their data carries
its household_id (HouseholdOwned) and tenancy.py keeps each session to one
household. All members of a household see the same data; receipts remember
who uploaded them. SQLite by default, any SQLAlchemy URL works (PostgreSQL).
"""

from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Time,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
    event,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declared_attr,
    mapped_column,
    relationship,
    sessionmaker,
)

from . import config
from .text import normalize


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Household(Base):
    """One household (tenant): its members and all of its data."""

    __tablename__ = "households"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HouseholdOwned:
    """Data of one household. tenancy.py adds the session's household to
    every query of such a row and to every new one."""

    @declared_attr
    def household_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    # usernames are unique across households: logging in names no household
    username: Mapped[str] = mapped_column(String(64), unique=True)
    # empty for the operator, who belongs to no household
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    is_operator: Mapped[bool] = mapped_column(Boolean, default=False)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    locale: Mapped[str] = mapped_column(String(8), default="de")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # admins add members, reset passwords and disable accounts
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # after a reset the one-time password only allows setting a new one
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    # part of every token; raising it ends all sessions of the account
    token_version: Mapped[int] = mapped_column(Integer, default=0)


class AppState(Base):
    """One-time data migrations that have run (key -> value)."""

    __tablename__ = "app_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256), default="")


class HouseholdSetting(HouseholdOwned, Base):
    """A household's settings (key -> value), e.g. the one-off threshold."""

    __tablename__ = "household_settings"
    __table_args__ = (UniqueConstraint("household_id", "key", name="uq_household_settings_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(256), default="")


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[int] = mapped_column(Integer)


class ApiToken(HouseholdOwned, Base):
    """A member's token for scripts on the host (upload receipts and bank
    statements, read everything the member reads). Shown once, stored as a
    hash, valid until revoked or until the account's token_version moves."""

    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # the last characters, so the owner can tell tokens apart
    hint: Mapped[str] = mapped_column(String(8))
    # users.token_version at creation: a password change or reset ends the token
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Category(HouseholdOwned, Base):
    """kind: "variable" (shopping, lifestyle), "fixed" (utilities, rent) or
    "income" (salary, child benefit) - only incoming bank bookings use the
    latter; an incoming booking in a spending category is a refund."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("household_id", "key", name="uq_categories_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(48))
    name_de: Mapped[str] = mapped_column(String(64))
    name_en: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16), default="variable")
    color: Mapped[str] = mapped_column(String(16), default="#64748b")
    icon: Mapped[str] = mapped_column(String(32), default="tag")
    # food or not, for the purchases overview (Jochen, 2026-10-28: per category)
    is_food: Mapped[bool] = mapped_column(Boolean, default=False)


class Store(HouseholdOwned, Base):
    __tablename__ = "stores"
    __table_args__ = (UniqueConstraint("household_id", "normalized", name="uq_stores_normalized"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    normalized: Mapped[str] = mapped_column(String(128))
    default_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))


class Receipt(HouseholdOwned, Base):
    """status: "draft" after reading, "confirmed" once a person checked it.
    Only confirmed receipts count in the statistics."""

    __tablename__ = "receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"))
    purchased_on: Mapped[date | None] = mapped_column(Date)
    # read from the receipt when printed, else empty
    purchased_at: Mapped[time | None] = mapped_column(Time)
    receipt_number: Mapped[str] = mapped_column(String(32), default="")
    # TSE (KassenSichV) transaction number and serial: one purchase per register,
    # so the same receipt read twice is recognised
    tse_transaction: Mapped[str] = mapped_column(String(64), default="")
    tse_serial: Mapped[str] = mapped_column(String(128), default="")
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    payment_method: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    source: Mapped[str] = mapped_column(String(16), default="photo")
    file_name: Mapped[str] = mapped_column(String(256), default="")
    media_type: Mapped[str] = mapped_column(String(64), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    # set when the file was deleted after the retention period
    file_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    store: Mapped[Store | None] = relationship()
    items: Mapped[list["ReceiptItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", order_by="ReceiptItem.position"
    )


class ReceiptItem(HouseholdOwned, Base):
    __tablename__ = "receipt_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(256))
    quantity: Mapped[float] = mapped_column(default=1.0)
    # what quantity counts: piece, kg or l (weighed goods: 0.532 kg)
    unit: Mapped[str] = mapped_column(String(8), default="piece")
    unit_price_cents: Mapped[int | None] = mapped_column(Integer)
    # the amount paid: printed price minus the article's discount
    total_cents: Mapped[int] = mapped_column(Integer)
    # a discount printed under the article ("Preisvorteil 0,30"), positive
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    discount_label: Mapped[str] = mapped_column(String(64), default="")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))

    receipt: Mapped[Receipt] = relationship(back_populates="items")


class CategoryRule(HouseholdOwned, Base):
    """Learned mapping from a normalized item text to a category."""

    __tablename__ = "category_rules"
    __table_args__ = (UniqueConstraint("household_id", "pattern", name="uq_category_rules_pattern"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(256))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    hits: Mapped[int] = mapped_column(Integer, default=0)


class MerchantRule(HouseholdOwned, Base):
    """A word in a bank counterparty ("rewe") that counts a payment in a
    category when nothing else decided it: no receipt, no fixed cost, no
    decision a person made for that counterparty."""

    __tablename__ = "merchant_rules"
    __table_args__ = (UniqueConstraint("household_id", "keyword", name="uq_merchant_rules_keyword"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    # normalized (text.normalize), matched as whole words
    keyword: Mapped[str] = mapped_column(String(64))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))


class Tag(HouseholdOwned, Base):
    """For whom or what for (a family member, a holiday), next to the one
    category of an entry (the what). Sums per tag may overlap."""

    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("household_id", "name", name="uq_tags_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(7), default="#64748b")


recurring_cost_tags = Table(
    "recurring_cost_tags",
    Base.metadata,
    Column("recurring_id", ForeignKey("recurring_costs.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

bank_transaction_tags = Table(
    "bank_transaction_tags",
    Base.metadata,
    Column("transaction_id", ForeignKey("bank_transactions.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class TagRule(HouseholdOwned, Base):
    """Learned tags of a bank counterparty (pattern as in CategoryRule)."""

    __tablename__ = "tag_rules"
    pattern: Mapped[str] = mapped_column(String(256), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class RecurringRule(HouseholdOwned, Base):
    """A bank counterparty learned to pay a recurring cost (pattern as in
    CategoryRule); one counterparty can pay several (gas and electricity)."""

    __tablename__ = "recurring_rules"
    pattern: Mapped[str] = mapped_column(String(256), primary_key=True)
    recurring_id: Mapped[int] = mapped_column(ForeignKey("recurring_costs.id", ondelete="CASCADE"), primary_key=True)


class RecurringCost(HouseholdOwned, Base):
    """A cost due every interval_months (1 = monthly instalment, 12 = yearly),
    spread evenly over its period in the statistics."""

    __tablename__ = "recurring_costs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    interval_months: Mapped[int] = mapped_column(Integer, default=1)
    start_on: Mapped[date] = mapped_column(Date)
    end_on: Mapped[date | None] = mapped_column(Date)
    # instalment for a utility meter: counts as "paid" in its settlement forecast
    meter_id: Mapped[int | None] = mapped_column(ForeignKey("meters.id", ondelete="SET NULL"))
    tags: Mapped[list[Tag]] = relationship(secondary=recurring_cost_tags, lazy="selectin", order_by=Tag.name)


class Meter(HouseholdOwned, Base):
    """A utility meter. kind: electricity, gas, water, heat or other."""

    __tablename__ = "meters"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="electricity")
    unit: Mapped[str] = mapped_column(String(16), default="kWh")
    meter_number: Mapped[str] = mapped_column(String(64), default="")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    # automatic reading (smartmeter.py): a device pushes with its token, or
    # the API polls source_url and reads the number at source_path
    ingest_token_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_url: Mapped[str] = mapped_column(String(512), default="")
    source_path: Mapped[str] = mapped_column(String(128), default="")
    last_ingest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ingest_error: Mapped[str] = mapped_column(String(256), default="")

    readings: Mapped[list["MeterReading"]] = relationship(
        back_populates="meter", cascade="all, delete-orphan", order_by="MeterReading.read_on"
    )
    tariffs: Mapped[list["Tariff"]] = relationship(cascade="all, delete-orphan", order_by="Tariff.valid_from")


class MeterReading(HouseholdOwned, Base):
    __tablename__ = "meter_readings"
    __table_args__ = (UniqueConstraint("meter_id", "read_on"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"))
    read_on: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column()
    source: Mapped[str] = mapped_column(String(16), default="manual")

    meter: Mapped[Meter] = relationship(back_populates="readings")


class Tariff(HouseholdOwned, Base):
    """Prices valid from a date on: gross cent per unit and gross base fee per month."""

    __tablename__ = "tariffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"))
    valid_from: Mapped[date] = mapped_column(Date)
    unit_price_ct: Mapped[float] = mapped_column()
    base_fee_monthly_cents: Mapped[int] = mapped_column(Integer, default=0)


class BankAccount(HouseholdOwned, Base):
    """One of the household's own accounts. Bookings of a statement belong to
    it; transfers to or from another own account count nowhere."""

    __tablename__ = "bank_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    bank: Mapped[str] = mapped_column(String(64), default="")
    # normalized (no spaces, upper case); empty when the statements never say
    iban: Mapped[str] = mapped_column(String(34), default="", index=True)
    # credit cards have no IBAN: the masked number of the card statement
    # ("4000********1234"); empty for giro and savings accounts
    card_number: Mapped[str] = mapped_column(String(19), default="", index=True)
    # "giro" or "savings": transfers to a savings account count as saved
    # (a credit card is recognised by its card_number)
    kind: Mapped[str] = mapped_column(String(16), default="giro")
    color: Mapped[str] = mapped_column(String(7), default="#64748b")


class BankTransaction(HouseholdOwned, Base):
    """One booking from a bank statement. amount_cents < 0 is money going out.

    status decides whether and how it counts, so nothing is counted twice:
    review    - not decided yet, does not count
    receipt   - the payment of a receipt (receipt_id); the receipt counts
    fixed     - covered by a recurring cost (recurring_id); that one counts
    counted   - counts itself in category_id (e.g. online shopping)
    ignored   - transfers, income, anything that is no spending
    """

    __tablename__ = "bank_transactions"
    # two households may import the same statement (a shared account)
    __table_args__ = (UniqueConstraint("household_id", "fingerprint", name="uq_bank_transactions_fingerprint"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    booked_on: Mapped[date] = mapped_column(Date, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    counterparty: Mapped[str] = mapped_column(String(256), default="")
    iban: Mapped[str] = mapped_column(String(34), default="")
    purpose: Mapped[str] = mapped_column(String(512), default="")
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="review", index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id", ondelete="SET NULL"))
    receipt_id: Mapped[int | None] = mapped_column(ForeignKey("receipts.id", ondelete="SET NULL"))
    recurring_id: Mapped[int | None] = mapped_column(ForeignKey("recurring_costs.id", ondelete="SET NULL"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    # card bookings: the settlement date of their card statement
    statement_on: Mapped[date | None] = mapped_column(Date)
    # who decided the status: "auto" (matching, re-matched after changes) or
    # "person" (kept when the app matches again)
    decided_by: Mapped[str] = mapped_column(String(8), default="auto")
    # a one-off (a gift, a car): counted apart, outside averages and balance
    one_off: Mapped[bool] = mapped_column(Boolean, default=False)
    # status ignored: this debit pays the statement of that card account
    settles_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # only for status counted: the booking's own tags
    tags: Mapped[list[Tag]] = relationship(secondary=bank_transaction_tags, lazy="selectin", order_by=Tag.name)


class UtilityBill(HouseholdOwned, Base):
    """An annual utility bill as read from its PDF or photo; amounts in cents."""

    __tablename__ = "utility_bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int | None] = mapped_column(ForeignKey("meters.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16), default="other")
    provider: Mapped[str] = mapped_column(String(128), default="")
    meter_number: Mapped[str] = mapped_column(String(64), default="")
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    consumption: Mapped[float | None] = mapped_column()
    unit: Mapped[str] = mapped_column(String(16), default="")
    total_cents: Mapped[int | None] = mapped_column(Integer)
    paid_cents: Mapped[int | None] = mapped_column(Integer)
    balance_cents: Mapped[int | None] = mapped_column(Integer)
    unit_price_ct: Mapped[float | None] = mapped_column()
    base_fee_monthly_cents: Mapped[int | None] = mapped_column(Integer)
    new_instalment_cents: Mapped[int | None] = mapped_column(Integer)
    file_name: Mapped[str] = mapped_column(String(256), default="")
    media_type: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# categories that count as food when they are created (changeable per household)
FOOD_CATEGORIES = ("groceries", "drinks")

DEFAULT_CATEGORIES = [
    # key, de, en, kind, color, icon
    ("groceries", "Lebensmittel", "Groceries", "variable", "#22c55e", "shopping-basket"),
    ("drinks", "Getränke", "Drinks", "variable", "#06b6d4", "cup-soda"),
    ("drugstore", "Drogerie", "Drugstore", "variable", "#a855f7", "sparkles"),
    ("household", "Haushalt", "Household", "variable", "#f59e0b", "spray-can"),
    ("lifestyle", "Lifestyle", "Lifestyle", "variable", "#ec4899", "heart"),
    ("eating_out", "Essen gehen", "Eating out", "variable", "#ef4444", "utensils"),
    ("clothing", "Kleidung", "Clothing", "variable", "#6366f1", "shirt"),
    ("transport", "Mobilität", "Transport", "variable", "#0ea5e9", "car"),
    ("deposit", "Pfand", "Deposit", "variable", "#94a3b8", "recycle"),
    ("other", "Sonstiges", "Other", "variable", "#64748b", "tag"),
    ("electricity", "Strom", "Electricity", "fixed", "#eab308", "zap"),
    ("gas", "Gas", "Gas", "fixed", "#f97316", "flame"),
    ("water", "Wasser", "Water", "fixed", "#3b82f6", "droplet"),
    ("housing", "Wohnen", "Housing", "fixed", "#14b8a6", "house"),
    ("subscriptions", "Abos & Verträge", "Subscriptions", "fixed", "#8b5cf6", "repeat"),
    ("salary", "Gehalt & Lohn", "Salary & wages", "income", "#15803d", "briefcase"),
    ("benefits", "Kindergeld & Leistungen", "Child benefit & benefits", "income", "#0f766e", "baby"),
    ("rent_income", "Mieteinnahmen", "Rental income", "income", "#4d7c0f", "key"),
    ("interest", "Zinsen & Dividenden", "Interest & dividends", "income", "#a16207", "piggy-bank"),
    ("other_income", "Sonstige Einnahmen", "Other income", "income", "#475569", "plus"),
]

# grocery chains whose payments count as groceries (Jochen, 2026-10-27);
# editable in the settings, seeded once
DEFAULT_MERCHANTS = {
    "groceries": [
        "aldi", "lidl", "netto", "edeka", "penny", "rewe", "norma", "kaufland",
        "marktkauf", "globus", "tegut", "famila", "nahkauf", "alnatura", "denns", "bio company",
    ],
}

engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    if config.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


MIGRATIONS = Path(__file__).parent / "migrations"


def migrate() -> None:
    """Brings the schema to the newest migration. The baseline also
    completes a database from before Alembic (tables and columns it lacks)."""
    from alembic import command
    from alembic.config import Config

    with engine.begin() as connection:
        alembic = Config()
        alembic.set_main_option("script_location", str(MIGRATIONS))
        alembic.attributes["connection"] = connection
        command.upgrade(alembic, "head")


# one-time data migrations, run in every household (markers in app_state)
_ONCE = ("income_v1", "recurring_rules_v1", "merchant_rules_v1")


def init_db() -> None:
    if config.DATABASE_URL.startswith("sqlite:///"):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    migrate()
    with SessionLocal() as session:
        pending = [key for key in _ONCE if session.get(AppState, key) is None]
        for household in session.scalars(select(Household)).all():
            tenancy.bind(session, household.id)
            # households from before the admin role: the first account becomes admin
            if session.scalar(select(User.id).where(User.is_admin)) is None:
                first = session.scalar(select(User).order_by(User.id).limit(1))
                if first is not None:
                    first.is_admin = True
            seed_household(session, merchants="merchant_rules_v1" in pending)
            if "income_v1" in pending:
                _reopen_income(session)
            if "recurring_rules_v1" in pending:
                _learn_recurring(session)
            session.flush()
        tenancy.bind(session, None)
        now = datetime.now(timezone.utc).isoformat()
        session.add_all(AppState(key=key, value=now) for key in pending)
        session.commit()


def seed_household(session: Session, merchants: bool = True) -> None:
    """The default categories a household lacks (a removed one comes back)
    and, for a new household, the default merchant list. Works on the
    household bound to the session."""
    existing = set(session.scalars(select(Category.key)))
    for key, de, en, kind, color, icon in DEFAULT_CATEGORIES:
        if key not in existing:
            session.add(Category(key=key, name_de=de, name_en=en, kind=kind, color=color, icon=icon, is_food=key in FOOD_CATEGORIES))
    session.flush()
    if not merchants:
        return
    for key, keywords in DEFAULT_MERCHANTS.items():
        category_id = session.scalar(select(Category.id).where(Category.key == key))
        if category_id is None:
            continue
        for keyword in keywords:
            if session.scalar(select(MerchantRule.id).where(MerchantRule.keyword == keyword)) is None:
                session.add(MerchantRule(keyword=keyword, category_id=category_id))


def get_setting(session: Session, key: str) -> str | None:
    """A setting of the household bound to the session."""
    return session.scalar(select(HouseholdSetting.value).where(HouseholdSetting.key == key))


def set_setting(session: Session, key: str, value: str) -> None:
    setting = session.scalar(select(HouseholdSetting).where(HouseholdSetting.key == key))
    if setting is None:
        session.add(HouseholdSetting(key=key, value=value))
    else:
        setting.value = value


def create_household(session: Session, name: str) -> Household:
    """A new household with its default categories and merchants; the
    session is bound to it afterwards."""
    household = Household(name=name)
    session.add(household)
    session.flush()
    tenancy.bind(session, household.id)
    seed_household(session)
    return household


def _learn_recurring(session: Session) -> None:
    """Bookings a person linked to a recurring cost before this was learned
    teach their counterparty (as banking.learn_recurring does)."""
    seen = set()
    for tx in session.scalars(select(BankTransaction).where(BankTransaction.status == "fixed", BankTransaction.recurring_id.is_not(None))):
        key = (("bank:" + normalize(tx.counterparty))[:256], tx.recurring_id)
        if tx.counterparty and key not in seen:
            seen.add(key)
            session.add(RecurringRule(pattern=key[0], recurring_id=key[1]))


def _reopen_income(session: Session) -> None:
    """Incoming bookings used to be ignored automatically; since income
    counts (2026-10), those that are no transfer or card debit wait for a
    decision (income category or refund) like any new one."""
    own = {iban for iban in session.scalars(select(BankAccount.iban)) if iban}
    for tx in session.scalars(
        select(BankTransaction).where(
            BankTransaction.status == "ignored",
            BankTransaction.amount_cents > 0,
            BankTransaction.settles_account_id.is_(None),
        )
    ):
        if "".join(tx.iban.split()).upper() not in own:
            tx.status = "review"


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session

from . import tenancy  # noqa: E402,F401  (registers the household filter)
