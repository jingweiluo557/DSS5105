"""Versioned working copies of scheduling review reasons."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision = '0007_drafts'
down_revision = '0006_dispatch'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('dispatch_drafts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('order_id', sa.String(32), nullable=False),
        sa.Column('review_id', sa.String(36), nullable=False),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('content', sa.Text().with_variant(LONGTEXT(), 'mysql'), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False))
    op.create_index('ix_dispatch_drafts_order_id', 'dispatch_drafts', ['order_id'])


def downgrade():
    op.drop_table('dispatch_drafts')
