"""Alerts: what would interrupt the manager right now, the policy behind it, shelving and feedback.

GET  /api/alerts/preview      evaluate the policy on the current snapshot (dry run; nothing sent, nothing recorded)
GET  /api/alerts/policy       the thresholds, tiers and caps
GET  /api/alerts/kpis         emails per week, items per digest, usefulness ratings
PUT  /api/alerts/shelve       mute a key or a kind until a date (X-Confirm-Write: true)
POST /api/alerts/feedback     the manager rates an alert useful / not useful
POST /api/internal/alerts/run scheduler tick (Bearer SCHEDULER_TOKEN); sends only when ALERT_EMAILS_ENABLED=true
"""
from __future__ import annotations

import secrets
from datetime import date, datetime

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..services import alert_policy
from ..services.alert_delivery import AlertDelivery
from ..services.scheduling_service import current_snapshot
from ..workflow_api import business_now

router = APIRouter(tags=['Alerts'])


def delivery(request: Request) -> AlertDelivery:
    return AlertDelivery(request.app.state.settings)


def snapshot_loader(request: Request):
    return lambda: current_snapshot(request.app.state.database, business_now().date().isoformat())


@router.get('/api/alerts/preview')
def preview(request: Request):
    svc = delivery(request)
    now = business_now()
    data = snapshot_loader(request)()
    decisions = svc.evaluate(data, now)
    body = alert_policy.summarize(decisions)
    body['business_now'] = now.isoformat()
    body['emails_enabled'] = bool(getattr(request.app.state.settings, 'alert_emails_enabled', False))
    body['would_send'] = alert_policy.render_email(decisions, now) or None
    return body


@router.get('/api/alerts/policy')
def policy():
    return alert_policy.summarize([])['policy'] | {
        'triggers': {
            'P1': ['stage below its same-weekday minimum for 3 consecutive working days',
                   'all active orders of a customer stalled while later-due orders moved',
                   'order due within 2 working days that cannot finish even in the best case, with no approved priority',
                   'a reminder the manager set fires (handled by the reminder service)'],
            'P2': ['newly overdue order', 'order newly rated high risk by the shared queue', 'new order of >= 1500 pieces or <= 12-day lead'],
            'P3': ['one day below the same-weekday range', 'order idle >= 5 calendar days', 'medium risk']},
        'anti_spam': ['dedupe key per alert; same key not re-emailed within its cooldown unless the score rose by 8+',
                      'an unresolved alert is reminded in the digest, never re-emailed on its own',
                      'at most 3 immediate emails a day; overflow goes to the digest',
                      'quiet hours 22:00-06:00 hold P2/P3', 'the manager can shelve a key or a kind for N days',
                      'clearing never emails; the briefing says "cleared"']}


@router.get('/api/alerts/kpis')
def kpis(request: Request):
    return delivery(request).ledger.kpis(business_now())


class Shelve(BaseModel):
    target: str = Field(min_length=3, max_length=120, description='an alert key (kind:entity) or a kind')
    days: int = Field(ge=1, le=90)
    set_by: str = Field(default='manager', max_length=100)


@router.put('/api/alerts/shelve')
def shelve(body: Shelve, request: Request, x_confirm_write: str = Header(default='')):
    from .security import require_manager
    require_manager(request)
    if x_confirm_write.lower() != 'true':
        raise HTTPException(409, 'Confirm the mute before saving.')
    now = business_now()
    until = date.fromordinal(now.date().toordinal() + body.days).isoformat() + 'T23:59:59+08:00'
    delivery(request).ledger.shelve(body.target, until, body.set_by, now)
    return {'target': body.target, 'until': until}


class Feedback(BaseModel):
    key: str = Field(min_length=3, max_length=120)
    useful: bool
    note: str = Field(default='', max_length=300)


@router.post('/api/alerts/feedback')
def feedback(body: Feedback, request: Request):
    delivery(request).ledger.feedback(body.key, body.useful, body.note, business_now())
    return {'recorded': True}


@router.post('/api/internal/alerts/run')
async def run(request: Request):
    settings = request.app.state.settings
    token = settings.scheduler_token.get_secret_value()
    if not token or not secrets.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer ' + token).encode()):
        raise HTTPException(401, 'Scheduler authentication required.')
    return await delivery(request).run(snapshot_loader(request))
