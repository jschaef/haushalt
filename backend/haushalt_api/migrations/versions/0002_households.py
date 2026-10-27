"""households: every row of data belongs to one household

An existing database becomes household 1, "Mein Haushalt" (Jochen,
2026-10-27): its members and all of its data. Unique keys (category key,
store, learned rules, merchant keyword, tag name, booking fingerprint) hold
per household from now on. The one-off threshold and the dashboard reset
date move from app_state to the household's settings.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

OWNED = (
    "categories", "stores", "receipts", "receipt_items", "category_rules", "merchant_rules", "tags",
    "tag_rules", "recurring_rules", "recurring_costs", "meters", "meter_readings", "tariffs",
    "bank_accounts", "bank_transactions", "utility_bills",
)
# table -> column that was unique on its own and is unique per household now
UNIQUE = {
    "categories": "key",
    "stores": "normalized",
    "category_rules": "pattern",
    "merchant_rules": "keyword",
    "tags": "name",
    "bank_transactions": "fingerprint",
}
SETTINGS = ("one_off_threshold_cents", "dashboard_since")
# SQLite reflects the old unnamed unique constraints under these names
_SQLITE_NAMES = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _unique_on(bind, table: str, column: str) -> str | None:
    """Name of the unique constraint on just this column ("" when SQLite
    left it unnamed, then the batch names it by _SQLITE_NAMES), None if
    there is none."""
    for constraint in sa.inspect(bind).get_unique_constraints(table):
        if constraint["column_names"] == [column]:
            return constraint["name"] or ""
    return None


def _has_rows(bind) -> bool:
    return any(bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() for table in ("users", *OWNED))


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "households",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    first = None
    if _has_rows(bind):
        bind.execute(
            sa.text("INSERT INTO households (name, disabled, created_at) VALUES ('Mein Haushalt', :off, CURRENT_TIMESTAMP)"),
            {"off": False},
        )
        first = bind.execute(sa.text("SELECT min(id) FROM households")).scalar()

    for table in OWNED:
        with op.batch_alter_table(table, naming_convention=_SQLITE_NAMES) as batch:
            batch.add_column(sa.Column("household_id", sa.Integer(), nullable=True))
        if first is not None:
            bind.execute(sa.text(f"UPDATE {table} SET household_id = :h"), {"h": first})
        with op.batch_alter_table(table, naming_convention=_SQLITE_NAMES) as batch:
            batch.alter_column("household_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(f"fk_{table}_household_id", "households", ["household_id"], ["id"], ondelete="CASCADE")
            batch.create_index(f"ix_{table}_household_id", ["household_id"], unique=False)
            column = UNIQUE.get(table)
            if column:
                old = _unique_on(bind, table, column)
                if old is not None:
                    batch.drop_constraint(old or f"uq_{table}_{column}", type_="unique")
                batch.create_unique_constraint(f"uq_{table}_{column}", ["household_id", column])

    with op.batch_alter_table("users", naming_convention=_SQLITE_NAMES) as batch:
        batch.add_column(sa.Column("household_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("is_operator", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_foreign_key("fk_users_household_id", "households", ["household_id"], ["id"], ondelete="CASCADE")
        batch.create_index("ix_users_household_id", ["household_id"], unique=False)
    if first is not None:
        bind.execute(sa.text("UPDATE users SET household_id = :h"), {"h": first})

    op.create_table(
        "household_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=256), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "key", name="uq_household_settings_key"),
    )
    op.create_index("ix_household_settings_household_id", "household_settings", ["household_id"], unique=False)
    for key in SETTINGS:
        value = bind.execute(sa.text("SELECT value FROM app_state WHERE key = :k"), {"k": key}).scalar()
        if value is not None and first is not None:
            bind.execute(
                sa.text("INSERT INTO household_settings (household_id, key, value) VALUES (:h, :k, :v)"),
                {"h": first, "k": key, "v": value},
            )
        bind.execute(sa.text("DELETE FROM app_state WHERE key = :k"), {"k": key})


def downgrade() -> None:
    raise NotImplementedError("restore the backup taken before the update")
