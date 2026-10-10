"""Shared tasks, observed KPI history and immutable daily briefings."""
import sqlalchemy as sa

metadata = sa.MetaData()
tasks = sa.Table('dashboard_tasks', metadata,
    sa.Column('id', sa.String(80), primary_key=True),
    sa.Column('order_id', sa.String(32)), sa.Column('title', sa.String(300), nullable=False),
    sa.Column('origin', sa.String(16), nullable=False), sa.Column('done', sa.Boolean, nullable=False),
    sa.Column('business_date', sa.String(10), nullable=False),
    sa.Column('reasons', sa.Text, nullable=False), sa.Column('version', sa.Integer, nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False), sa.Column('updated_at', sa.String(40), nullable=False))
briefings = sa.Table('dashboard_briefings', metadata,
    sa.Column('day', sa.String(10), primary_key=True),
    sa.Column('business_date', sa.String(10), nullable=False),
    sa.Column('generated_at', sa.String(40), nullable=False), sa.Column('payload', sa.Text, nullable=False))
metrics = sa.Table('dashboard_metrics', metadata,
    sa.Column('business_date', sa.String(10), primary_key=True), sa.Column('payload', sa.Text, nullable=False))
