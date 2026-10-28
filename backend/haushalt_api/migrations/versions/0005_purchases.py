"""purchases overview: food categories and units of receipt items

Food or not is set per category (Jochen, 2026-10-28); groceries and drinks
start as food. Receipt items get a unit (piece, kg, l); items read before
count as pieces until they are read again.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_food", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(sa.text("UPDATE categories SET is_food = :yes WHERE key IN ('groceries', 'drinks')").bindparams(yes=True))

    with op.batch_alter_table("receipt_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("unit", sa.String(length=8), nullable=False, server_default="piece"))


def downgrade() -> None:
    with op.batch_alter_table("receipt_items", schema=None) as batch_op:
        batch_op.drop_column("unit")

    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.drop_column("is_food")
