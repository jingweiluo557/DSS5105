"""Who the morning email goes to, and when it was sent (briefing_email_deliveries)."""
from alembic import op
from app.briefing_email import deliveries, metadata

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    # create_all skips tables that exist: a database created from 0005 after this table was added already has it.
    metadata.create_all(op.get_bind())


def downgrade():
    deliveries.drop(op.get_bind(), checkfirst=True)
