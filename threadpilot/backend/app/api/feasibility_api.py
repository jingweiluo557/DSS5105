"""Feasibility for the UI: the same estimate_capacity tool the chat uses, plus the rows for the capacity chart.

POST /api/feasibility/estimate {quantity, product, due_date, delivery_point?, packing_loss_days?, delivery_buffer_days?}
Returns the tool result (queue projection, AFT band, worst case) and a `chart` block: per stage the pieces already
queued at or before that stage, the new order, and the pieces the stage can complete before the due date.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..schemas import Slots
from ..workflow_api import business_now
from ..workflow_tools import resolve_date

router = APIRouter(prefix='/api/feasibility', tags=['Feasibility'])


class EstimateRequest(BaseModel):
    quantity: int = Field(gt=0, le=100000)
    product: str = Field(min_length=1, max_length=60)
    due_date: str = Field(min_length=3, max_length=40, description='ISO date, "the 25th", "this Saturday", "in 10 working days"')
    delivery_point: Literal['factory', 'customer'] = 'factory'
    packing_loss_days: int | None = Field(default=None, ge=0, le=60)
    delivery_buffer_days: int | None = Field(default=None, ge=0, le=60)


@router.post('/estimate')
def estimate(body: EstimateRequest, request: Request):
    now = business_now()
    tools = request.app.state.workflow.tools
    slots = Slots(quantity=body.quantity, product=body.product, due_date=resolve_date(body.due_date, now).isoformat(),
                  delivery_point=body.delivery_point, packing_loss_days=body.packing_loss_days, delivery_buffer_days=body.delivery_buffer_days)
    data, evidence = tools.capacity(slots, now)
    return {'business_date': now.date().isoformat(), 'request': slots.model_dump(exclude_none=True), 'estimate': data,
            'chart': chart_rows(data, body.quantity), 'evidence_count': len(evidence)}


def chart_rows(data: dict, quantity: int) -> dict:
    """Rows for a stacked bar per stage: queued pieces + the new order against capacity to the due date.

    capacity_to_due = historical pieces/day (last 20 non-Sunday days) x available workdays, the same inputs as the
    worst-case estimate; queue_capacity_to_due uses the queue simulation's capacity (previous eight same weekdays x
    completion factor) when available. The bottleneck is the stage with the highest load-to-capacity ratio.
    """
    workdays = data['available_workdays']
    queue = data.get('queue_projection') or {}
    qcap = queue.get('capacity_per_day') or {}
    rows = []
    for s in data['stages']:
        cap = round(s['historical_pieces_per_day'] * workdays)
        rows.append({'stage': s['stage'], 'queued_pieces': s['backlog_pieces'], 'new_order_pieces': quantity,
                     'capacity_to_due': cap, 'queue_capacity_to_due': round(qcap[s['stage']] * workdays) if qcap.get(s['stage']) else None,
                     'rate_per_day': s['historical_pieces_per_day'], 'load_pct_of_capacity': round(100 * (s['backlog_pieces'] + quantity) / cap) if cap else None})
    bottleneck = max(rows, key=lambda r: r['load_pct_of_capacity'] or 0)['stage'] if rows else None
    return {'available_workdays': workdays, 'due_date': data['due_date'], 'rows': rows, 'bottleneck': bottleneck,
            'verdict': data.get('verdict'), 'preliminary': data.get('preliminary'),
            'expected_finish': queue.get('expected_case', {}).get('finish_date'), 'best_finish': queue.get('best_case', {}).get('finish_date'),
            'p_on_time_for_size': (data.get('historical_lead_time_model') or {}).get('p_on_time'),
            'reading': 'A stage whose stacked bar rises above its capacity line cannot clear the queue plus the new order before the due date on historical rates. '
                       'Stages run in series, so the final output date is the queue projection, not the sum of the bars.'}
