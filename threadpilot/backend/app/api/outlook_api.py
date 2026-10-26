"""Authenticated, explicitly confirmed personal Outlook integration."""
import logging
import re
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from .security import require_admin, confirm_write
from ..services.outlook_service import OutlookService, network_error_guard

router = APIRouter(prefix='/api/outlook', tags=['Outlook'])
COOKIE = 'threadpilot_outlook_flow'


class RedactOAuthQuery(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if str(args[2]).split('?')[0] == '/api/outlook/callback':
                args[2] = '/api/outlook/callback'
                record.args = tuple(args)
        return True


logging.getLogger('uvicorn.access').addFilter(RedactOAuthQuery())


def service(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return OutlookService(request.app.state.settings)


class SendEmail(BaseModel):
    id: UUID
    to: list[str] = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=12000)
    confirmed: Literal[True]

    @field_validator('to')
    @classmethod
    def addresses(cls, values):
        values = list(dict.fromkeys(v.strip() for v in values))
        if any(len(v) > 254 or not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+', v) for v in values):
            raise ValueError('Enter valid recipient email addresses.')
        return values

    @field_validator('subject', 'body')
    @classmethod
    def content(cls, value, info):
        value = value.strip()
        if not value or '\x00' in value or (info.field_name == 'subject' and any(c in value for c in '\r\n')):
            raise ValueError('Enter a valid subject and body.')
        return value


@router.get('/status', dependencies=[Depends(require_admin)])
def status(svc=Depends(service)):
    return svc.status()


@router.post('/connect', dependencies=[Depends(require_admin)])
def connect(request: Request, response: Response, source: Literal['settings', 'test'] = 'test', svc=Depends(service)):
    url, binding = network_error_guard(svc.begin)
    same_site = 'none' if svc.settings.outlook_redirect_uri.startswith('https:') else 'lax'
    response.set_cookie(COOKIE, binding, max_age=600, httponly=True, samesite=same_site,
                        secure=svc.settings.outlook_redirect_uri.startswith('https:'), path='/api/outlook/callback')
    response.set_cookie(COOKIE + '_source', source, max_age=600, httponly=True, samesite=same_site,
                        secure=svc.settings.outlook_redirect_uri.startswith('https:'), path='/api/outlook/callback')
    return {'authorization_url': url}


@router.get('/callback')
def callback(request: Request, svc=Depends(service)):
    try:
        network_error_guard(lambda: svc.finish(dict(request.query_params), request.cookies.get(COOKIE, '')))
        outcome = 'connected'
    except HTTPException:
        outcome = 'failed'
    target = '/?authorization=' + outcome + '#/settings' if request.cookies.get(COOKIE + '_source') == 'settings' else '/outlook.html?authorization=' + outcome
    target = svc.settings.public_frontend_origin.rstrip('/') + target
    response = RedirectResponse(target, status_code=303,
                                headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
    response.delete_cookie(COOKIE, path='/api/outlook/callback')
    response.delete_cookie(COOKIE + '_source', path='/api/outlook/callback')
    return response


@router.post('/disconnect', dependencies=[Depends(confirm_write)])
def disconnect(svc=Depends(service)):
    svc.disconnect()
    return {'connected': False}


@router.post('/send', dependencies=[Depends(confirm_write)])
def send(body: SendEmail, svc=Depends(service)):
    return network_error_guard(lambda: svc.send(str(body.id), body.model_dump(exclude={'id', 'confirmed'})))


@router.get('/messages', dependencies=[Depends(require_admin)])
def messages(svc=Depends(service)):
    return {'messages': svc.history()}
