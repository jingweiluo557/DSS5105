"""场景 1.2/2.1：前端和原有意图工具使用同一数据库。"""
from datetime import datetime, timezone
from sqlalchemy import select
from ..crud.data_record import MODELS, fields
from ..db.session import Database
from ..schemas import Evidence
from ..workflow_tools import DataTools


class DatabaseDataTools(DataTools):
    freshness = 'queried current database records; freshness depends on upstream API/file synchronization'

    def __init__(self, database: Database) -> None:
        """场景 1.1–3.3：保留原业务算法，仅替换存储适配器。"""
        self.database = database

    def briefing(self) -> dict | None:
        """The newest saved morning briefing, read from the same database as the dashboard."""
        return _newest_briefing(self.database)

    def rows(self, source: str) -> list[Evidence]:
        """场景 1.2：每次打开新事务读取已提交数据，证据使用稳定记录 ID。"""
        name = source.removesuffix('.csv')
        if name not in MODELS:
            raise ValueError('Unsupported source')
        with self.database.sessions() as session:
            model = MODELS[name]
            return [Evidence(source=name, row=r.id, url=f'/api/evidence/{name}/{r.id}',
                             record={k: '' if v is None else str(v) for k, v in fields(name, r).items()}, record_id=r.id, version=r.version, updated_at=r.updated_at.isoformat() + 'Z', original_source=r.source)
                    for r in session.scalars(select(model).order_by(model.id))]


def _newest_briefing(database: Database) -> dict | None:
    """The newest row of dashboard_briefings (one per day, saved at 07:00), or None when none has been saved yet."""
    import json
    import sqlalchemy as sa
    from ..dashboard_store import briefings
    if not sa.inspect(database.engine).has_table(briefings.name):
        return None
    with database.engine.connect() as db:
        row = db.execute(sa.select(briefings).order_by(briefings.c.day.desc()).limit(1)).mappings().first()
    return None if row is None else {'day': row['day'], 'business_date': row['business_date'], 'generated_at': row['generated_at'], **json.loads(row['payload'])}


def snapshot(database: Database, today: str) -> dict:
    """场景 1.2/2.1：请求时生成快照，文件导出仅供下载，不作问答缓存。"""
    result: dict = {'today': today, 'generated_at': datetime.now(timezone.utc).isoformat()}
    with database.sessions() as session:
        for name, model in MODELS.items():
            ordering = (model.date, model.id) if name == 'production_log' else (model.id,)
            result[name] = [{**{k: '' if v is None else str(v) for k, v in fields(name, r).items()}, '_record_id': r.id, '_version': r.version}
                            for r in session.scalars(select(model).order_by(*ordering))]
    return result
