"""Saved morning briefing email drafts."""
from alembic import op
from app.briefing_email import metadata

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind())


def downgrade():
    metadata.drop_all(op.get_bind())
