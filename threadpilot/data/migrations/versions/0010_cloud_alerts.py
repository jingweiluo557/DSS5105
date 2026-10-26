"""Add shared alert history, shelves, digests and feedback; preserve existing data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision = '0010_cloud_alerts'
down_revision = '0009_cloud_mail'
branch_labels = None
depends_on = None


def upgrade():
    large = sa.Text().with_variant(LONGTEXT(), 'mysql')
    def col(name, length=64, **kw):
        return sa.Column(name, sa.String(length), **kw)
    op.create_table('alert_decisions', col('id', primary_key=True), col('key', 160),
        col('kind'), col('tier', 16), sa.Column('score', sa.Integer), col('channel'),
        sa.Column('reason', sa.Text), col('sent_at'), col('business_date', 10),
        sa.Column('payload', large), col('email_id'), col('email_status'))
    op.create_table('alert_shelves', col('target', 160, primary_key=True), col('until'), col('set_by', 100), col('set_at'))
    op.create_table('alert_digests', col('id', primary_key=True), col('sent_at'), col('business_date', 10), sa.Column('keys', large), col('email_status'))
    op.create_table('alert_feedback', col('id', primary_key=True), col('key', 160), sa.Column('useful', sa.Integer), col('note', 300), col('at'))


def downgrade():
    for name in ('alert_feedback', 'alert_digests', 'alert_shelves', 'alert_decisions'):
        op.drop_table(name)
