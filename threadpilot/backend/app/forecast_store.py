"""Versioned imported forecasts with original inputs and model evidence."""
import hashlib
import json
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT
from .sql_workflow_store import SQLWorkflowStore

metadata = sa.MetaData()
large = sa.Text().with_variant(LONGTEXT(), 'mysql')
batches = sa.Table('prediction_batches', metadata,
    sa.Column('id', sa.String(64), primary_key=True), sa.Column('business_date', sa.String(10), nullable=False),
    sa.Column('imported_at', sa.String(40), nullable=False), sa.Column('source_file', sa.String(200), nullable=False),
    sa.Column('model', large, nullable=False), sa.Column('sources', large, nullable=False))
predictions = sa.Table('order_predictions', metadata,
    # Batch and rows are inserted in one transaction; imported batches are immutable.
    sa.Column('batch_id', sa.String(64), primary_key=True),
    sa.Column('order_id', sa.String(32), primary_key=True), sa.Column('delay_probability', sa.Float, nullable=False),
    sa.Column('risk_level', sa.String(16), nullable=False), sa.Column('estimated_completion_date', sa.String(10)),
    sa.Column('suggested_workshop', sa.String(32)), sa.Column('total_estimated_days', sa.Float),
    sa.Column('exported_at', sa.String(40), nullable=False), sa.Column('payload', large, nullable=False))

def import_forecasts(database, asset):
    batch_id = hashlib.sha256(json.dumps(asset, sort_keys=True).encode()).hexdigest()
    source_orders = {r['order_id']:r for r in asset['sources']['orders'] if r['status']=='IN_PROGRESS'}
    if set(asset['forecasts']) != set(source_orders): raise ValueError('Forecast coverage must match active source orders.')
    store = SQLWorkflowStore(database.engine)
    with database.engine.begin() as db:
        store.upsert(db, batches, {'id':batch_id,'business_date':asset['business_date'],
            'imported_at':datetime.now(timezone.utc).isoformat(),'source_file':'in_progress_orders_forecast_full.json',
            'model':json.dumps(asset['model']), 'sources':json.dumps(asset['sources'])})
        for oid, row in asset['forecasts'].items():
            p=row['prediction'];c=row['completion'];prob=p['delay_probability']
            if not 0 <= prob <= 1: raise ValueError('Invalid probability.')
            expected='HIGH' if prob>=.6 else 'MEDIUM' if prob>=.35 else 'LOW'
            if p['risk_level']!=expected: raise ValueError('Inconsistent risk label.')
            store.upsert(db, predictions, {'batch_id':batch_id,'order_id':oid,'delay_probability':prob,
                'risk_level':p['risk_level'],'estimated_completion_date':c['forecast']['estimated_completion_date'],
                'suggested_workshop':c['workshop']['workshop_id'],'total_estimated_days':c['forecast']['total_estimated_days'],
                'exported_at':row['exported_at'],'payload':json.dumps(row)})
    return {'batch_id':batch_id,'rows':len(asset['forecasts'])}

def load_forecasts(database):
    with database.engine.connect() as db:
        batch=db.execute(sa.select(batches).order_by(batches.c.imported_at.desc(), batches.c.id).limit(1)).mappings().first()
        if batch is None: return {'business_date':'','sources':{},'forecasts':{},'model':{}}
        rows=db.execute(sa.select(predictions).where(predictions.c.batch_id==batch['id'])).mappings().all()
    return {'batch_id':batch['id'],'business_date':batch['business_date'],'imported_at':batch['imported_at'],
            'source_file':batch['source_file'],'model':json.loads(batch['model']),'sources':json.loads(batch['sources']),
            'forecasts':{r['order_id']:json.loads(r['payload']) for r in rows}}
