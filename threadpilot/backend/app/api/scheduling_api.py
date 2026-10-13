from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from ..services.scheduling_service import SchedulingService, QueueAnalysis, current_snapshot
from ..workflow_api import business_now

router = APIRouter(prefix='/api/scheduling', tags=['Scheduling'])


def confirm_decision(x_confirm_write: str = Header(default='')) -> None:
    if x_confirm_write.lower() != 'true':
        raise HTTPException(409, {'code': 'CONFIRMATION_REQUIRED',
                                 'message': 'Review the impact, then submit X-Confirm-Write: true.'})


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['save', 'apply', 'reject']
    reviewed_by: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)

    draft_id: UUID | None = None
    draft_version: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def draft_pair(self):
        if (self.draft_id is None) != (self.draft_version is None):
            raise ValueError('Draft ID and version are required together.')
        return self

    @field_validator('reviewed_by', 'note')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Reviewer and decision reason are required.')
        return value.strip()


@router.get('/risk')
def risk(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return QueueAnalysis(current_snapshot(request.app.state.database, business_now().date().isoformat())).summary()


@router.post('/orders/{order_id}/preview')
def preview(order_id: str, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return SchedulingService(request.app.state.database).preview(order_id, business_now().date().isoformat())


@router.post('/reviews/{review_id}/decision', dependencies=[Depends(confirm_decision)])
def decide(review_id: UUID, body: Decision, request: Request):
    try:
        return SchedulingService(request.app.state.database).decide(str(review_id), body.decision, body.reviewed_by,
                                                                    body.note, business_now().date().isoformat(),
                                                                    str(body.draft_id) if body.draft_id else None, body.draft_version)
    except KeyError:
        raise HTTPException(404, 'Review not found.')
    except ValueError as error:
        raise HTTPException(409, str(error))


@router.get('/history')
def history(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return SchedulingService(request.app.state.database).history()


class DraftEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    text: str | None = Field(default=None, max_length=2000)
    reviewer: str | None = Field(default=None, max_length=100)
    decision: Literal['save', 'apply', 'reject'] | None = None


class DraftTurn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    instruction: str = Field(default='请起草审核理由。', min_length=1, max_length=1500)


def draft_service(request):
    from ..services.review_drafts import ReviewDraftService
    return ReviewDraftService(request.app.state.database)


def draft_result(call):
    from ..services.review_drafts import DraftConflict
    try:
        return call()
    except KeyError:
        raise HTTPException(404, 'Draft not found.')
    except DraftConflict as error:
        raise HTTPException(409, str(error))
    except ValueError as error:
        raise HTTPException(422, str(error))


@router.post('/orders/{order_id}/draft')
def open_draft(order_id: str, request: Request):
    return draft_result(lambda: draft_service(request).open(order_id, business_now().date().isoformat()))


@router.get('/drafts/{draft_id}')
def get_draft(draft_id: UUID, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return draft_result(lambda: draft_service(request).get(str(draft_id), business_now().date().isoformat()))


@router.patch('/drafts/{draft_id}')
def edit_draft(draft_id: UUID, body: DraftEdit, request: Request):
    return draft_result(lambda: draft_service(request).change(str(draft_id), body.version,
                        business_now().date().isoformat(), text=body.text, reviewer=body.reviewer, decision=body.decision))


@router.post('/drafts/{draft_id}/{action}')
async def draft_action(draft_id: UUID, action: Literal['generate', 'adopt', 'refresh'], body: DraftTurn, request: Request):
    from ..services.review_drafts import DraftConflict
    from openai import OpenAIError
    service = draft_service(request)
    today = business_now().date().isoformat()
    if action != 'generate':
        return draft_result(lambda: service.change(str(draft_id), body.version, today,
                            adopt=action == 'adopt', refresh=action == 'refresh'))
    try:
        settings = request.app.state.settings
        return await service.generate(str(draft_id), body.version, today, body.instruction,
                                      request.app.state.client, settings.openai_model, settings.intent_api_style)
    except KeyError:
        raise HTTPException(404, 'Draft not found.')
    except DraftConflict as error:
        raise HTTPException(409, str(error))
    except ValueError as error:
        raise HTTPException(422, str(error))
    except OpenAIError:
        raise HTTPException(502, 'AI is temporarily unavailable. Saved text is retained; retry or edit manually.')
