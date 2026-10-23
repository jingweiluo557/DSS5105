"""Minute timer entry point; due decisions always use the shared business clock."""
import asyncio
import secrets
from fastapi import APIRouter, HTTPException, Request
from ..services.briefing_delivery import BriefingDelivery
from ..services.scheduled_email import ScheduledEmail

router = APIRouter(tags=['Email scheduler'])

@router.post('/api/internal/email/run')
async def run_email(request: Request):
    settings = request.app.state.settings
    token = settings.scheduler_token.get_secret_value()
    if not token or not secrets.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer ' + token).encode()):
        raise HTTPException(401, 'Scheduler authentication required.')
    # Independent durable claims prevent duplicate sends across concurrent ticks.
    briefing, scheduled = await asyncio.gather(
        BriefingDelivery(settings).run(request.app), ScheduledEmail(settings).run())
    return {'briefing': briefing, 'scheduled': scheduled}
