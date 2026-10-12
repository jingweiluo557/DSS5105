"""Imported order prediction batches and per-order forecasts."""
from alembic import op
from app.forecast_store import metadata
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

def upgrade():
    metadata.create_all(op.get_bind())

def downgrade():
    metadata.drop_all(op.get_bind())
