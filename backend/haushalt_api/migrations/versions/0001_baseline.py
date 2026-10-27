"""baseline: schema as of 2026-10-27

Revision ID: 0001
Revises: -
Create Date: 2026-10-27 08:31:06.488902
"""

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('app_state',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', sa.String(length=256), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('bank_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('bank', sa.String(length=64), nullable=False),
    sa.Column('iban', sa.String(length=34), nullable=False),
    sa.Column('card_number', sa.String(length=19), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bank_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bank_accounts_card_number'), ['card_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_accounts_iban'), ['iban'], unique=False)

    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=48), nullable=False),
    sa.Column('name_de', sa.String(length=64), nullable=False),
    sa.Column('name_en', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('color', sa.String(length=16), nullable=False),
    sa.Column('icon', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('revoked_tokens',
    sa.Column('jti', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('jti')
    )
    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=128), nullable=False),
    sa.Column('password_hash', sa.String(length=256), nullable=False),
    sa.Column('locale', sa.String(length=8), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('disabled', sa.Boolean(), nullable=False),
    sa.Column('must_change_password', sa.Boolean(), nullable=False),
    sa.Column('token_version', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('category_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pattern', sa.String(length=256), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('hits', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pattern')
    )
    op.create_table('merchant_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('keyword', sa.String(length=64), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('keyword')
    )
    op.create_table('meters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('unit', sa.String(length=16), nullable=False),
    sa.Column('meter_number', sa.String(length=64), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('ingest_token_hash', sa.String(length=64), nullable=False),
    sa.Column('source_url', sa.String(length=512), nullable=False),
    sa.Column('source_path', sa.String(length=128), nullable=False),
    sa.Column('last_ingest_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_ingest_error', sa.String(length=256), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('meters', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_meters_ingest_token_hash'), ['ingest_token_hash'], unique=False)

    op.create_table('stores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('normalized', sa.String(length=128), nullable=False),
    sa.Column('default_category_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['default_category_id'], ['categories.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('normalized')
    )
    op.create_table('tag_rules',
    sa.Column('pattern', sa.String(length=256), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('pattern', 'tag_id')
    )
    op.create_table('meter_readings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('meter_id', sa.Integer(), nullable=False),
    sa.Column('read_on', sa.Date(), nullable=False),
    sa.Column('value', sa.Double(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.ForeignKeyConstraint(['meter_id'], ['meters.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('meter_id', 'read_on')
    )
    op.create_table('receipts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=True),
    sa.Column('purchased_on', sa.Date(), nullable=True),
    sa.Column('total_cents', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('payment_method', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('file_name', sa.String(length=256), nullable=False),
    sa.Column('media_type', sa.String(length=64), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('file_deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('extraction', sa.JSON(), nullable=True),
    sa.Column('error', sa.String(length=512), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_receipts_sha256'), ['sha256'], unique=False)

    op.create_table('recurring_costs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('amount_cents', sa.Integer(), nullable=False),
    sa.Column('interval_months', sa.Integer(), nullable=False),
    sa.Column('start_on', sa.Date(), nullable=False),
    sa.Column('end_on', sa.Date(), nullable=True),
    sa.Column('meter_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['meter_id'], ['meters.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tariffs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('meter_id', sa.Integer(), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('unit_price_ct', sa.Double(), nullable=False),
    sa.Column('base_fee_monthly_cents', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['meter_id'], ['meters.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('utility_bills',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('meter_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('provider', sa.String(length=128), nullable=False),
    sa.Column('meter_number', sa.String(length=64), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=True),
    sa.Column('period_end', sa.Date(), nullable=True),
    sa.Column('consumption', sa.Double(), nullable=True),
    sa.Column('unit', sa.String(length=16), nullable=False),
    sa.Column('total_cents', sa.Integer(), nullable=True),
    sa.Column('paid_cents', sa.Integer(), nullable=True),
    sa.Column('balance_cents', sa.Integer(), nullable=True),
    sa.Column('unit_price_ct', sa.Double(), nullable=True),
    sa.Column('base_fee_monthly_cents', sa.Integer(), nullable=True),
    sa.Column('new_instalment_cents', sa.Integer(), nullable=True),
    sa.Column('file_name', sa.String(length=256), nullable=False),
    sa.Column('media_type', sa.String(length=64), nullable=False),
    sa.Column('error', sa.String(length=512), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['meter_id'], ['meters.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('booked_on', sa.Date(), nullable=False),
    sa.Column('amount_cents', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('counterparty', sa.String(length=256), nullable=False),
    sa.Column('iban', sa.String(length=34), nullable=False),
    sa.Column('purpose', sa.String(length=512), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=True),
    sa.Column('receipt_id', sa.Integer(), nullable=True),
    sa.Column('recurring_id', sa.Integer(), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('statement_on', sa.Date(), nullable=True),
    sa.Column('decided_by', sa.String(length=8), nullable=False),
    sa.Column('one_off', sa.Boolean(), nullable=False),
    sa.Column('settles_account_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['bank_accounts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['receipt_id'], ['receipts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['recurring_id'], ['recurring_costs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['settles_account_id'], ['bank_accounts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fingerprint')
    )
    with op.batch_alter_table('bank_transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bank_transactions_booked_on'), ['booked_on'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_transactions_status'), ['status'], unique=False)

    op.create_table('receipt_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('receipt_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=256), nullable=False),
    sa.Column('quantity', sa.Double(), nullable=False),
    sa.Column('unit_price_cents', sa.Integer(), nullable=True),
    sa.Column('total_cents', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['receipt_id'], ['receipts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('recurring_cost_tags',
    sa.Column('recurring_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['recurring_id'], ['recurring_costs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('recurring_id', 'tag_id')
    )
    op.create_table('recurring_rules',
    sa.Column('pattern', sa.String(length=256), nullable=False),
    sa.Column('recurring_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['recurring_id'], ['recurring_costs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('pattern', 'recurring_id')
    )
    op.create_table('bank_transaction_tags',
    sa.Column('transaction_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['transaction_id'], ['bank_transactions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('transaction_id', 'tag_id')
    )


def downgrade() -> None:
    op.drop_table('bank_transaction_tags')
    op.drop_table('recurring_rules')
    op.drop_table('recurring_cost_tags')
    op.drop_table('receipt_items')
    with op.batch_alter_table('bank_transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bank_transactions_status'))
        batch_op.drop_index(batch_op.f('ix_bank_transactions_booked_on'))

    op.drop_table('bank_transactions')
    op.drop_table('utility_bills')
    op.drop_table('tariffs')
    op.drop_table('recurring_costs')
    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_receipts_sha256'))

    op.drop_table('receipts')
    op.drop_table('meter_readings')
    op.drop_table('tag_rules')
    op.drop_table('stores')
    with op.batch_alter_table('meters', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_meters_ingest_token_hash'))

    op.drop_table('meters')
    op.drop_table('merchant_rules')
    op.drop_table('category_rules')
    op.drop_table('users')
    op.drop_table('tags')
    op.drop_table('revoked_tokens')
    op.drop_table('categories')
    with op.batch_alter_table('bank_accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bank_accounts_iban'))
        batch_op.drop_index(batch_op.f('ix_bank_accounts_card_number'))

    op.drop_table('bank_accounts')
    op.drop_table('app_state')
