"""Durable workflow and SQL conversation tables for HTTP functions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    def col(name, length=64, **kw):
        return sa.Column(name, sa.String(length), **kw)
    large = sa.Text().with_variant(LONGTEXT(), 'mysql')
    op.create_table('workflow_sessions', col('id', primary_key=True), sa.Column('state', large, nullable=False))
    op.create_table('workflow_sql_sessions', col('id', primary_key=True), sa.Column('history', large, nullable=False))
    op.create_table('workflow_actions', col('id', primary_key=True), col('session_id', nullable=False),
        col('kind', nullable=False), col('order_id', nullable=False), sa.Column('payload', large, nullable=False),
        col('status', nullable=False), col('created_at', nullable=False), sa.Column('receipt', large))
    op.create_table('workflow_reminders', col('id', primary_key=True), col('session_id', nullable=False),
        col('order_id', nullable=False), col('condition', nullable=False), col('deadline', nullable=False),
        col('since', nullable=False), sa.Column('evaluated', sa.Integer, nullable=False),
        sa.UniqueConstraint('session_id', 'order_id', 'condition', name='uq_workflow_reminder'))
    op.create_table('workflow_replies', col('event_id', 100, primary_key=True), col('order_id', nullable=False), col('received_at', nullable=False))
    op.create_table('workflow_notifications', col('id', 160, primary_key=True), col('session_id', nullable=False),
        col('order_id', nullable=False), sa.Column('message', sa.Text, nullable=False), col('created_at', nullable=False))


def downgrade():
    for name in ('notifications', 'replies', 'reminders', 'actions', 'sql_sessions', 'sessions'):
        op.drop_table('workflow_' + name)
