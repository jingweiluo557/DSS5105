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
    workflow = request.app.state.workflow
    async def update_order_watches():
        # The in-app briefing is independent of the Outlook send preference.
        now = workflow.clock()
        try:
            await asyncio.to_thread(workflow.order_records.evaluate, now)
            if await asyncio.to_thread(workflow.order_records.briefing_due, now):
                from .morning_api import generate_morning
                await generate_morning(request.app, scheduled=True)
            return 'checked'
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Order watch check will retry on the next timer tick')
            return 'retry_pending'

    # Independent durable claims prevent duplicate sends across concurrent ticks.
    briefing, scheduled, watches = await asyncio.gather(
        BriefingDelivery(settings).run(request.app), ScheduledEmail(settings).run(), update_order_watches())
    # Alert policy on the same tick (dry run unless ALERT_EMAILS_ENABLED=true); never blocks the briefing.
    try:
        from .alerts_api import delivery, snapshot_loader
        alerts = await delivery(request).run(snapshot_loader(request))
    except Exception as error:  # a policy error must not stop the briefing or scheduled emails
        alerts = {'status': 'error', 'message': str(error)[:200]}
    return {'briefing': briefing, 'scheduled': scheduled, 'alerts': alerts, 'order_watches': watches}
