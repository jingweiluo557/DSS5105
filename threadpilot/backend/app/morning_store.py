"""Immutable model-generated reports, separate from legacy rule summaries."""
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT
from .db.base import Base

reports = sa.Table('ai_morning_reports', Base.metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('day', sa.String(10), nullable=False),
    sa.Column('business_date', sa.String(10), nullable=False),
    sa.Column('generated_at', sa.String(40), nullable=False),
    sa.Column('fingerprint', sa.String(64), nullable=False),
    sa.Column('payload', sa.Text().with_variant(LONGTEXT(), 'mysql'), nullable=False))
