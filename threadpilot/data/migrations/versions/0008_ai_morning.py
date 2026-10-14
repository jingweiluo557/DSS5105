"""Grounded model-generated morning reports."""
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT
from alembic import op

revision = '0008_ai_morning'
down_revision = '0007_drafts'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ai_morning_reports',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('day', sa.String(10), nullable=False),
        sa.Column('business_date', sa.String(10), nullable=False),
        sa.Column('generated_at', sa.String(40), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('payload', sa.Text().with_variant(LONGTEXT(), 'mysql'), nullable=False))


def downgrade():
    op.drop_table('ai_morning_reports')
