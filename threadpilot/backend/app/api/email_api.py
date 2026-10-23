"""Email settings protected by the application's workspace access middleware."""
from fastapi import APIRouter, Depends, Request, Response, Header, HTTPException
from ..services.email_settings import EmailSettings, EmailPreferences
from ..services.briefing_delivery import BriefingDelivery
from ..business_clock import BusinessClock
from pydantic import BaseModel, AwareDatetime, Field, model_validator
from typing import Literal

router = APIRouter(prefix='/api/email', tags=['Email settings'])


def confirm_email_write(x_confirm_write: str = Header(default='')):
    if x_confirm_write.lower() != 'true':
        raise HTTPException(409, 'Confirm the email settings change before saving.')


def service(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return EmailSettings(request.app.state.settings)


@router.get('/settings')
def settings(request: Request, svc=Depends(service)):
    return {'preferences': svc.read(), 'connection': svc.outlook.status(),
            'clock': BusinessClock(request.app.state.settings).status(),
            'scheduler_enabled': request.app.state.settings.email_scheduler_enabled}


class ClockChange(BaseModel):
    mode: Literal['live','demo']
    target: AwareDatetime | None = None
    version: int = Field(ge=0)

    @model_validator(mode='after')
    def require_target(self):
        if self.mode == 'demo' and self.target is None:
            raise ValueError('Choose the demo date and time.')
        if self.target and not 2000 <= self.target.year <= 2100:
            raise ValueError('Choose a business date between 2000 and 2100.')
        return self


@router.get('/clock')
def clock_status(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return BusinessClock(request.app.state.settings).status()


@router.put('/clock', dependencies=[Depends(confirm_email_write)])
def set_clock(body: ClockChange, request: Request):
    return BusinessClock(request.app.state.settings).save(body.mode, body.target, body.version)


@router.put('/settings', dependencies=[Depends(confirm_email_write)])
def save(body: EmailPreferences, svc=Depends(service)):
    return {'preferences': svc.save(body)}


@router.get('/activity')
def activity(request: Request, svc=Depends(service)):
    rows = BriefingDelivery(request.app.state.settings).history()
    from ..services.scheduled_email import ScheduledEmail
    rows += ScheduledEmail(request.app.state.settings).history()
    rows = sorted(rows, key=lambda r:r['created_at'], reverse=True)[:100]
    return {'entries': [{k: v for k, v in row.items() if k not in ('lease', 'retry_at','storage_key','due_real')}
                        for row in rows]}


@router.post('/connect', dependencies=[Depends(confirm_email_write)])
def connect(request: Request, response: Response, svc=Depends(service)):
    from .outlook_api import connect as connect_outlook
    return connect_outlook(request, response, source='settings', svc=svc.outlook)


@router.post('/disconnect', dependencies=[Depends(confirm_email_write)])
def disconnect(svc=Depends(service)):
    svc.outlook.disconnect()
    return {'connected': False}
