"""One shared dispatch queue and immutable manager decisions."""
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT
from .db.base import Base

large = sa.Text().with_variant(LONGTEXT(), 'mysql')
schedule = sa.Table('dispatch_schedule', Base.metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('version', sa.Integer, nullable=False),
    sa.Column('priority', large, nullable=False))
reviews = sa.Table('dispatch_reviews', Base.metadata,
    sa.Column('id', sa.String(36), primary_key=True),
    sa.Column('order_id', sa.String(32), nullable=False),
    sa.Column('fingerprint', sa.String(64), nullable=False),
    sa.Column('payload', large, nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('status', sa.String(20), nullable=False),
    sa.Column('decision', sa.String(20)),
    sa.Column('reviewed_by', sa.String(100)),
    sa.Column('note', sa.Text),
    sa.Column('decided_at', sa.String(40)))

# Working drafts are separate from immutable review decisions.
drafts = sa.Table('dispatch_drafts', Base.metadata,
    sa.Column('id', sa.String(36), primary_key=True),
    sa.Column('order_id', sa.String(32), nullable=False, index=True),
    sa.Column('review_id', sa.String(36), nullable=False),
    sa.Column('version', sa.Integer, nullable=False),
    sa.Column('status', sa.String(20), nullable=False),
    sa.Column('content', large, nullable=False),
    sa.Column('updated_at', sa.String(40), nullable=False))
