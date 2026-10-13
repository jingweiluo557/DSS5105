from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
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
                                                                    body.note, business_now().date().isoformat())
    except KeyError:
        raise HTTPException(404, 'Review not found.')
    except ValueError as error:
        raise HTTPException(409, str(error))


@router.get('/history')
def history(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return SchedulingService(request.app.state.database).history()
