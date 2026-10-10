import asyncio
import logging
import secrets
from datetime import datetime, date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from .. import briefing_email
from sqlalchemy.exc import SQLAlchemyError
from ..services.dashboard_service import DashboardService, LOCAL
from ..services.snapshot_service import snapshot
from ..sql_workflow_store import WorkflowBusy
from ..workflow_api import business_now
from ..forecast_store import load_forecasts
from ..services.dashboard_service import forecast_matches, analyze

router = APIRouter(prefix='/api', tags=['Dashboard'])

def current(request):
    return snapshot(request.app.state.database, business_now().date().isoformat())

class NewTask(BaseModel):
    id: UUID
    title: str = Field(min_length=1, max_length=300)

class TaskUpdate(BaseModel):
    done: bool
    version: int = Field(ge=1)

class EmailUpdate(BaseModel):
    subject: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=12000)
    version: int = Field(ge=1)

    @field_validator('subject', 'body')
    @classmethod
    def clean(cls, value, info):
        value = value.strip()
        if not value or '\x00' in value or (info.field_name == 'subject' and any(c in value for c in '\r\n')):
            raise ValueError('Enter a valid subject and body.')
        return value

@router.post('/dashboard/briefings/{day}/email')
def generate_email(day: date, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return briefing_email.generate(request.app.state.database, day.isoformat())
    except KeyError:
        raise HTTPException(404, 'No saved briefing is available for this date.')

@router.put('/dashboard/briefings/{day}/email')
def save_email(day: date, body: EmailUpdate, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    result = briefing_email.save(request.app.state.database, day.isoformat(), body.subject, body.body, body.version)
    if result is None:
        raise HTTPException(409, 'This draft changed on another device. Reopen it before saving.')
    return result

@router.get('/dashboard')
def dashboard(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return DashboardService(request.app.state.database).get(current(request))
    except WorkflowBusy:
        raise HTTPException(409, 'Dashboard is updating. Please retry.')

@router.post('/dashboard/tasks', status_code=201)
def add_task(body: NewTask, request: Request):
    task_id = DashboardService(request.app.state.database).create_task(body.title, business_now().date().isoformat(), datetime.now(LOCAL), body.id)
    return {'id': task_id}

@router.put('/dashboard/tasks/{task_id}')
def update_task(task_id: str, body: TaskUpdate, request: Request):
    if not DashboardService(request.app.state.database).complete_task(task_id, body.done, body.version, datetime.now(LOCAL)):
        raise HTTPException(409, 'Task changed on another device. Refresh and retry.')
    return {'status': 'saved'}

def generate_morning(app):
    data = snapshot(app.state.database, business_now().date().isoformat())
    return DashboardService(app.state.database).generate_due(data, datetime.now(LOCAL))

@router.post('/internal/briefings/run')
def run_briefing(request: Request):
    token = request.app.state.settings.scheduler_token.get_secret_value()
    if not token or not secrets.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer ' + token).encode()):
        raise HTTPException(401, 'Scheduler authentication required.')
    try:
        return generate_morning(request.app)
    except WorkflowBusy:
        return {'status': 'already_running'}

@router.get('/predictions')
def prediction_list(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    data=current(request)
    asset=load_forecasts(request.app.state.database)
    valid=forecast_matches(data,asset)
    source={r['order_id']:r for r in asset['sources'].get('orders',[])}
    rows=[]
    for oid,row in asset['forecasts'].items():
        c=row['completion']
        rows.append({**source[oid], **row['prediction'], 'estimated_completion_date':c['forecast']['estimated_completion_date'],
                     'total_estimated_days':c['forecast']['total_estimated_days'], 'workshop':c['workshop'],
                     'exported_at':row['exported_at']})
    return {'batch_id':asset.get('batch_id'), 'business_date':asset['business_date'], 'current_business_date':data['today'],
            'imported_at':asset.get('imported_at'), 'valid':valid, 'rows':rows, 'model':asset['model']}

@router.get('/predictions/{order_id}')
def prediction_source(order_id: str, request: Request):
    asset=load_forecasts(request.app.state.database)
    row=asset['forecasts'].get(order_id)
    if row is None: raise HTTPException(404,'Prediction not found.')
    return {'order_id':order_id,'business_date':asset['business_date'],'batch_id':asset['batch_id'],
            'imported_at':asset['imported_at'],'source_file':asset['source_file'], 'model':asset['model'],
            'valid_for_current_data':forecast_matches(current(request),asset), **row}

@router.get('/dashboard/sources/{kind}')
def diagnosis_source(kind: str, request: Request):
    if kind not in ('priority','production','capacity'): raise HTTPException(404,'Source not found.')
    data=current(request);asset=load_forecasts(request.app.state.database);result=analyze(data,asset)
    if kind=='priority':
        return {'business_date':data['today'],'calculation':'Late: active and due_date < business date. At risk: not late and imported probability >= 0.6; rule score >= 60 only when forecast is unavailable.',
                'forecast':result['forecast'],'batch_id':asset.get('batch_id'),'health':result['health'],
                'orders':result['orders']}
    if kind=='production':
        return {'business_date':data['today'],'calculation':'Latest recorded working-day output against prior 20 working days; Sundays excluded. Stage totals are not order-level output.',
                'comparison':result['production'],'records':data['production_log']}
    return {'business_date':data['today'],'calculation':'Full order quantity / (capacity * (1 - defect rate)) + queue days + pickup days. ACTIVE compatible workshops within batch limits only. Exclusive capacity; no joint allocation.',
            'orders':data['orders'],'workshops':data['workshops']}

async def morning_loop(app):
    while True:
        try:
            await asyncio.to_thread(generate_morning, app)
        except (SQLAlchemyError, WorkflowBusy, ValueError, OSError):
            logging.getLogger(__name__).warning('Morning briefing pending; next check will retry')
        await asyncio.sleep(30)
