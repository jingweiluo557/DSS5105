"""Record order stage/status transitions in the same transaction as the order."""
from alembic import op
import sqlalchemy as sa

revision = '0011_order_history'
down_revision = '0010_cloud_alerts'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('order_status_journal',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('order_id', sa.String(32), nullable=False),
        sa.Column('business_day', sa.String(10), nullable=False),
        sa.Column('event', sa.String(24), nullable=False))
    op.create_index('ix_order_status_journal_order_id', 'order_status_journal', ['order_id'])


def downgrade():
    op.drop_table('order_status_journal')
