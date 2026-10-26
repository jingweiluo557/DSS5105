"""Shared encrypted mail state and business clock for stateless deployments.

The small SQLite-compatible facade is limited to the application's fixed store
statements. Values remain bound parameters. A durable lock row serializes each
store transaction across workers; runtime users need no DDL privileges.
"""
import re
from contextlib import contextmanager
from functools import lru_cache
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT, insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from .db.base import Base
from .db.session import make_engine

large = sa.Text().with_variant(LONGTEXT(), 'mysql')
locks = sa.Table('app_state_locks', Base.metadata,
    sa.Column('name', sa.String(32), primary_key=True))
tables = {
    'vault': sa.Table('mail_vault', Base.metadata,
        sa.Column('name', sa.String(128), primary_key=True), sa.Column('value', large, nullable=False)),
    'sends': sa.Table('mail_sends', Base.metadata,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('payload', large, nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('created', sa.Float, nullable=False)),
    'briefing_deliveries': sa.Table('mail_briefing_deliveries', Base.metadata,
        sa.Column('day', sa.String(128), primary_key=True), sa.Column('payload', large, nullable=False)),
    'scheduled_emails': sa.Table('mail_scheduled_emails', Base.metadata,
        sa.Column('id', sa.String(64), primary_key=True), sa.Column('payload', large, nullable=False)),
    'clock': sa.Table('business_clock', Base.metadata,
        sa.Column('id', sa.Integer, primary_key=True), sa.Column('payload', large, nullable=False)),
}

@lru_cache(maxsize=8)
def engine_for(url):
    return make_engine(url)

class Row:
    def __init__(self, row): self.row = row
    def __getitem__(self, key):
        return self.row[key] if isinstance(key, int) else self.row._mapping[key]

class Result:
    def __init__(self, result): self.result = result
    @property
    def rowcount(self): return self.result.rowcount
    def fetchone(self):
        row = self.result.fetchone()
        return Row(row) if row is not None else None
    def fetchall(self): return [Row(row) for row in self.result.fetchall()]
    def __iter__(self): return iter(self.fetchall())

class Store:
    def __init__(self, connection, group):
        self.connection, self.group = connection, group
        self.begin()

    def insert(self, table):
        return mysql_insert(table) if self.connection.dialect.name == 'mysql' else sqlite_insert(table)

    def begin(self):
        if self.connection.dialect.name == 'sqlite':
            self.connection.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            self.connection.begin()
        statement = self.insert(locks).values(name=self.group)
        if self.connection.dialect.name == 'mysql':
            statement = statement.on_duplicate_key_update(name=statement.inserted.name)
        else:
            statement = statement.on_conflict_do_nothing()
        self.connection.execute(statement)
        self.connection.execute(sa.select(locks).where(locks.c.name == self.group).with_for_update())

    def commit(self): self.connection.commit()

    def execute(self, sql, params=()):
        if sql == 'BEGIN IMMEDIATE':
            self.begin()
            return None
        if sql.startswith('CREATE TABLE IF NOT EXISTS '):
            name = sql.split()[5]
            if name not in tables: raise ValueError('Unknown state table')
            return None  # Alembic owns schema creation in database mode.
        match = re.fullmatch(r'INSERT OR (REPLACE|IGNORE) INTO (\w+) VALUES \((.*)\)', sql)
        if match:
            mode, name, raw = match.groups()
            table = tables[name]
            bound = iter(params)
            values = [next(bound) if token.strip() == '?' else int(token.strip()) for token in raw.split(',')]
            statement = self.insert(table).values(dict(zip(table.c.keys(), values, strict=True)))
            if self.connection.dialect.name == 'mysql':
                if mode == 'IGNORE':
                    statement = statement.prefix_with('IGNORE')
                else:
                    statement = statement.on_duplicate_key_update(**{
                        c.name: statement.inserted[c.name] for c in table.c if not c.primary_key})
            else:
                statement = statement.on_conflict_do_nothing() if mode == 'IGNORE' else statement.on_conflict_do_update(
                    index_elements=list(table.primary_key.columns), set_={c.name: statement.excluded[c.name] for c in table.c if not c.primary_key})
            return Result(self.connection.execute(statement))
        if not sql.startswith(('SELECT ', 'UPDATE ', 'DELETE ')):
            raise ValueError('Unsupported state statement')
        for old, table in tables.items():
            sql = re.sub(r'\b' + old + r'\b', table.name, sql)
        pieces = sql.split('?')
        if len(pieces) != len(params) + 1: raise ValueError('Parameter count mismatch')
        sql = pieces[0] + ''.join(f':p{i}' + part for i, part in enumerate(pieces[1:]))
        return Result(self.connection.execute(sa.text(sql), {f'p{i}': value for i, value in enumerate(params)}))

@contextmanager
def shared_store(settings, group='email'):
    with engine_for(settings.database_url.get_secret_value()).connect() as connection:
        store = Store(connection, group)
        try:
            yield store
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

def read_clock(settings):
    # A non-locking read can be nested inside the email claim transaction.
    with engine_for(settings.database_url.get_secret_value()).connect() as connection:
        return connection.execute(sa.select(tables['clock'].c.payload).where(tables['clock'].c.id == 1)).scalar_one_or_none()
