"""Shared dashboard tasks and scheduled daily briefings."""
from alembic import op
from app.dashboard_store import metadata

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

def upgrade():
    metadata.create_all(op.get_bind())

def downgrade():
    metadata.drop_all(op.get_bind())
