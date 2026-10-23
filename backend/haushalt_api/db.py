"""Database models (SQLAlchemy 2). Money is stored as integer cents.

All members of the household see the same data; receipts remember who
uploaded them. SQLite by default, any SQLAlchemy URL works (PostgreSQL).
"""

from datetime import date, datetime, timezone
from typing import Iterator

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
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
    mapped_column,
    relationship,
    sessionmaker,
)

from . import config


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    locale: Mapped[str] = mapped_column(String(8), default="de")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[int] = mapped_column(Integer)


class Category(Base):
    """kind: "variable" (shopping, lifestyle) or "fixed" (utilities, rent)."""

    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(48), unique=True)
    name_de: Mapped[str] = mapped_column(String(64))
    name_en: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16), default="variable")
    color: Mapped[str] = mapped_column(String(16), default="#64748b")
    icon: Mapped[str] = mapped_column(String(32), default="tag")


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    normalized: Mapped[str] = mapped_column(String(128), unique=True)
    default_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))


class Receipt(Base):
    """status: "draft" after reading, "confirmed" once a person checked it.
    Only confirmed receipts count in the statistics."""

    __tablename__ = "receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"))
    purchased_on: Mapped[date | None] = mapped_column(Date)
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


class ReceiptItem(Base):
    __tablename__ = "receipt_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(256))
    quantity: Mapped[float] = mapped_column(default=1.0)
    unit_price_cents: Mapped[int | None] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))

    receipt: Mapped[Receipt] = relationship(back_populates="items")


class CategoryRule(Base):
    """Learned mapping from a normalized item text to a category."""

    __tablename__ = "category_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(256), unique=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    hits: Mapped[int] = mapped_column(Integer, default=0)


class RecurringCost(Base):
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


class Meter(Base):
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


class MeterReading(Base):
    __tablename__ = "meter_readings"
    __table_args__ = (UniqueConstraint("meter_id", "read_on"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"))
    read_on: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column()
    source: Mapped[str] = mapped_column(String(16), default="manual")

    meter: Mapped[Meter] = relationship(back_populates="readings")


class Tariff(Base):
    """Prices valid from a date on: gross cent per unit and gross base fee per month."""

    __tablename__ = "tariffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"))
    valid_from: Mapped[date] = mapped_column(Date)
    unit_price_ct: Mapped[float] = mapped_column()
    base_fee_monthly_cents: Mapped[int] = mapped_column(Integer, default=0)


class BankTransaction(Base):
    """One booking from a bank statement. amount_cents < 0 is money going out.

    status decides whether and how it counts, so nothing is counted twice:
    review    - not decided yet, does not count
    receipt   - the payment of a receipt (receipt_id); the receipt counts
    fixed     - covered by a recurring cost (recurring_id); that one counts
    counted   - counts itself in category_id (e.g. online shopping)
    ignored   - transfers, income, anything that is no spending
    """

    __tablename__ = "bank_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    booked_on: Mapped[date] = mapped_column(Date, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    counterparty: Mapped[str] = mapped_column(String(256), default="")
    iban: Mapped[str] = mapped_column(String(34), default="")
    purpose: Mapped[str] = mapped_column(String(512), default="")
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="review", index=True)
    receipt_id: Mapped[int | None] = mapped_column(ForeignKey("receipts.id", ondelete="SET NULL"))
    recurring_id: Mapped[int | None] = mapped_column(ForeignKey("recurring_costs.id", ondelete="SET NULL"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UtilityBill(Base):
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
]

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


def init_db() -> None:
    if config.DATABASE_URL.startswith("sqlite:///"):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _add_missing_columns()
    with SessionLocal() as session:
        existing = set(session.scalars(select(Category.key)))
        for key, de, en, kind, color, icon in DEFAULT_CATEGORIES:
            if key not in existing:
                session.add(Category(key=key, name_de=de, name_en=en, kind=kind, color=color, icon=icon))
        session.commit()


# Columns added after the first release. create_all() creates new tables but
# never alters existing ones, so older databases get them here.
_LATER_COLUMNS = {
    "receipts": {"file_deleted_at": "TIMESTAMP WITH TIME ZONE"},
    "recurring_costs": {"meter_id": "INTEGER REFERENCES meters(id) ON DELETE SET NULL"},
    "meters": {
        "ingest_token_hash": "VARCHAR(64) NOT NULL DEFAULT ''",
        "source_url": "VARCHAR(512) NOT NULL DEFAULT ''",
        "source_path": "VARCHAR(128) NOT NULL DEFAULT ''",
        "last_ingest_at": "TIMESTAMP WITH TIME ZONE",  # valid in SQLite and PostgreSQL
        "last_ingest_error": "VARCHAR(256) NOT NULL DEFAULT ''",
    },
}


def _add_missing_columns() -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in _LATER_COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
