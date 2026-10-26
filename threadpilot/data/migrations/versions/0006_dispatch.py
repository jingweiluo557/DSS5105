"""Manager-reviewed dispatch priorities and decision history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision = '0006_dispatch'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    large = sa.Text().with_variant(LONGTEXT(), 'mysql')
    op.create_table('dispatch_schedule', sa.Column('id', sa.Integer, primary_key=True),
                    sa.Column('version', sa.Integer, nullable=False), sa.Column('priority', large, nullable=False))
    op.create_table('dispatch_reviews', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('order_id', sa.String(32), nullable=False),
                    sa.Column('fingerprint', sa.String(64), nullable=False), sa.Column('payload', large, nullable=False),
                    sa.Column('created_at', sa.String(40), nullable=False), sa.Column('status', sa.String(20), nullable=False),
                    sa.Column('decision', sa.String(20)), sa.Column('reviewed_by', sa.String(100)),
                    sa.Column('note', sa.Text), sa.Column('decided_at', sa.String(40)))


def downgrade():
    op.drop_table('dispatch_reviews')
    op.drop_table('dispatch_schedule')
