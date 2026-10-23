"""Durable encrypted mail state and shared business clock; additive only."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision = '0009_cloud_mail'
down_revision = '0008_ai_morning'
branch_labels = None
depends_on = None

def upgrade():
    large = sa.Text().with_variant(LONGTEXT(), 'mysql')
    op.create_table('app_state_locks', sa.Column('name', sa.String(32), primary_key=True))
    op.create_table('mail_vault', sa.Column('name', sa.String(128), primary_key=True), sa.Column('value', large, nullable=False))
    op.create_table('mail_sends', sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('fingerprint', sa.String(64), nullable=False), sa.Column('payload', large, nullable=False),
        sa.Column('status', sa.String(32), nullable=False), sa.Column('created', sa.Float, nullable=False))
    op.create_table('mail_briefing_deliveries', sa.Column('day', sa.String(128), primary_key=True), sa.Column('payload', large, nullable=False))
    op.create_table('mail_scheduled_emails', sa.Column('id', sa.String(64), primary_key=True), sa.Column('payload', large, nullable=False))
    op.create_table('business_clock', sa.Column('id', sa.Integer, primary_key=True), sa.Column('payload', large, nullable=False))

def downgrade():
    for name in ('business_clock', 'mail_scheduled_emails', 'mail_briefing_deliveries', 'mail_sends', 'mail_vault', 'app_state_locks'):
        op.drop_table(name)
