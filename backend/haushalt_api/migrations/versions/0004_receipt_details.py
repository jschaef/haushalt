"""receipt details: article discounts, purchase time, receipt and TSE numbers

A discount printed under an article belongs to that article (Jochen,
2026-10-28); the time, the receipt number and the TSE transaction are kept
when printed, and the TSE transaction recognises a receipt read twice.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("receipt_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("discount_cents", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("discount_label", sa.String(length=64), nullable=False, server_default=""))

    with op.batch_alter_table("receipts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("purchased_at", sa.Time(), nullable=True))
        batch_op.add_column(sa.Column("receipt_number", sa.String(length=32), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("tse_transaction", sa.String(length=64), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("tse_serial", sa.String(length=128), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("receipts", schema=None) as batch_op:
        batch_op.drop_column("tse_serial")
        batch_op.drop_column("tse_transaction")
        batch_op.drop_column("receipt_number")
        batch_op.drop_column("purchased_at")

    with op.batch_alter_table("receipt_items", schema=None) as batch_op:
        batch_op.drop_column("discount_label")
        batch_op.drop_column("discount_cents")
