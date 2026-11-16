"""store comparison: a generic comparison name per receipt item

The model names every article generically ("Vollmilch 3,5 % 1 l") so the
same product can be compared across shops (Jochen, 2026-11-16). Items read
before stay NULL until they are named once (text only, on request).

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("receipt_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("compare_name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("receipt_items", schema=None) as batch_op:
        batch_op.drop_column("compare_name")
