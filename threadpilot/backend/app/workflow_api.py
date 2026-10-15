"""场景 1.1–3.3：在原 FastAPI 应用中增加有状态 JSON/SSE 接口。"""
import asyncio
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import AwareDatetime, BaseModel, Field

from .intent_classifier import IntentClassifier
from .conversation import ConversationAgent
from .services.review_drafts import DraftConflict
from .schemas import ChatRequest, ChatResponse, Evidence
from .streaming import event
from .workflow_engine import WorkflowEngine
from .workflow_store import WebhookSender, WorkflowStore
from .sql_workflow_store import SQLWorkflowStore, WorkflowBusy
from .services.snapshot_service import DatabaseDataTools
from sqlalchemy.exc import SQLAlchemyError


def business_now() -> datetime:
    """场景 1.2/3.3：默认复现数据日期；设 BUSINESS_NOW=live 后使用实际时钟。"""
    value = os.getenv('BUSINESS_NOW', 'live')
    if value == 'live':
        return datetime.now(timezone(timedelta(hours=8)))
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('BUSINESS_NOW must include timezone')
    return result


def initialize_workflow(app: FastAPI, data: Path, backend: Path) -> None:
    """场景 1.1–3.3：复用现有客户端，业务数据和私有 SQLite 分离。"""
    sender_url = os.getenv('CHASE_WEBHOOK_URL', '')
    sender = WebhookSender(sender_url, os.getenv('CHASE_WEBHOOK_TOKEN', '')) if sender_url else None
    store = (SQLWorkflowStore(app.state.database.engine) if app.state.settings.workflow_storage == 'database'
             else WorkflowStore(app.state.settings.workflow_db))
    app.state.workflow = WorkflowEngine(DatabaseDataTools(app.state.database), store, business_now, sender)
    from .services.review_chat import review_reason_handler
    app.state.workflow.review_reason_handler = review_reason_handler(app)
    async def morning_handler(classification, state, now):
        from .api.morning_api import generate_morning
        from .schemas import ToolCall, Intent
        report=(await generate_morning(app))['report']
        state.last_intent=Intent.MORNING_BRIEFING
        state.pending_clarification=None
        answer='\n\n'.join(label+': '+report[key] for label,key in [('Production review','yesterday'),('Priority issue','top_issue'),('Manager decisions','decide'),('Calculation basis','production_note')])
        answer+='\n\nBusiness date: '+report['business_date']+'; Generated: '+report['generated_at']+'. Open the briefing page to view the supporting records.'
        return app.state.workflow.response(state,classification,now,answer,
            [ToolCall(name='generate_morning_briefing',result={'report_id':report['id'],'model':report['model']})],[])
    app.state.workflow.morning_handler=morning_handler


async def monitor_loop(app: FastAPI) -> None:
    """场景 3.3：周期评估已经确认的提醒；数据故障保留未评估状态重试。"""
    while True:
        try:
            engine = app.state.workflow
            async with engine.lock:
                engine.store.evaluate_reminders(engine.clock(), engine.tools)
        except (OSError, ValueError, sqlite3.Error, SQLAlchemyError, WorkflowBusy):
            logging.getLogger(__name__).warning('Reminder source unavailable; pending checks retained')
        await asyncio.sleep(30)


class ReplyEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    order_id: str = Field(pattern=r'^ORD-\d{3}$')
    received_at: AwareDatetime


def install_workflow_routes(app: FastAPI, data: Path) -> None:
    """场景 1.1–3.3：保留原接口并增加完整工作流、证据和通知入口。"""
    async def run(body: ChatRequest, request: Request, emit=None) -> ChatResponse:
        """场景 1.1–3.3：映射模型与数据错误，不泄露上游异常文本。"""
        if not body.message.strip():
            raise HTTPException(422, {'code': 'EMPTY_MESSAGE', 'message': 'Message cannot be blank.'})
        classifier = getattr(app.state, 'intent_classifier', None)
        if classifier is None:
            classifier = ConversationAgent(app.state.client, app.state.settings.openai_model, app.state.settings.intent_api_style)
        try:
            result = await app.state.workflow.chat(body, classifier, emit=emit)
            return result.model_copy(update={'request_id': request.state.request_id, 'model': os.getenv('OPENAI_MODEL', 'gpt-4.1')})
        except WorkflowBusy:
            raise HTTPException(409, {'code': 'SESSION_BUSY', 'message': 'This conversation is processing another request. Retry shortly.'})
        except DraftConflict as error:
            raise HTTPException(409, {'code': 'DRAFT_CHANGED', 'message': str(error)})
        except KeyError:
            raise HTTPException(404, {'code': 'UNKNOWN_SESSION', 'message': 'Start a new conversation.'})
        except APITimeoutError:
            raise HTTPException(504, {'code': 'MODEL_TIMEOUT', 'message': 'Classification timed out.'})
        except RateLimitError:
            raise HTTPException(429, {'code': 'MODEL_RATE_LIMITED', 'message': 'Provider quota or rate limit reached.'})
        except (APIConnectionError, APIStatusError):
            raise HTTPException(502, {'code': 'MODEL_API_ERROR', 'message': 'Classification provider unavailable.'})
        except (OSError, SQLAlchemyError):
            raise HTTPException(503, {'code': 'DATA_UNAVAILABLE', 'message': 'Source data is unavailable.'})
        except ValueError:
            raise HTTPException(422, {'code': 'INVALID_WORKFLOW_INPUT', 'message': 'Unknown record, invalid date or invalid structured model output. Please clarify or retry.'})

    @app.post('/chat', response_model=ChatResponse, tags=['Workflow'])
    @app.post('/api/v1/workflow/chat', response_model=ChatResponse, tags=['Workflow'])
    async def workflow_chat(body: ChatRequest, request: Request) -> ChatResponse:
        """场景 1.1–3.3：JSON 工作流入口，传回 session_id 延续上下文。"""
        return await run(body, request)

    @app.post('/api/internal/reminders/run', tags=['Internal'])
    def evaluate_scheduled_reminders(request: Request) -> dict[str, str]:
        token = request.app.state.settings.scheduler_token.get_secret_value()
        if not token or not secrets.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer ' + token).encode()):
            raise HTTPException(401, {'code': 'UNAUTHORIZED', 'message': 'Scheduler authentication required.'})
        engine = app.state.workflow
        try:
            engine.store.evaluate_reminders(engine.clock(), engine.tools)
        except WorkflowBusy:
            return {'status': 'already_running'}
        return {'status': 'completed'}

    @app.post('/api/v1/workflow/chat/stream', tags=['Workflow'], response_class=StreamingResponse,
              responses={200: {'description': 'Validated workflow SSE: start, delta, done',
                               'content': {'text/event-stream': {'schema': {'type': 'string'}}}}})
    async def workflow_stream(body: ChatRequest, request: Request) -> StreamingResponse:
        """场景 1.1–3.3：完成规则验证后发送 SSE，避免未验证文本抢先展示。"""
        async def frames() -> AsyncIterator[str]:
            queue = asyncio.Queue(maxsize=32)
            emitted = False
            async def emit(text):
                nonlocal emitted
                emitted = True
                await queue.put(('delta', {'text':text}))
            async def produce():
                try:
                    result = await run(body, request, emit)
                    if not emitted:
                        await emit(result.answer)
                    await queue.put(('done', result.model_dump(mode='json')))
                except HTTPException as error:
                    detail = error.detail if isinstance(error.detail, dict) else {'message':str(error.detail)}
                    await queue.put(('error', {**detail,'request_id':request.state.request_id}))
                except Exception:
                    logging.getLogger(__name__).exception('Conversation stream failed')
                    await queue.put(('error', {'message':'Generation interrupted. Please retry.','request_id':request.state.request_id}))
            worker = asyncio.create_task(produce())
            try:
                yield event('start', {'request_id':request.state.request_id})
                while True:
                    try:
                        kind, payload = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ': keep-alive\n\n'
                        continue
                    yield event(kind, payload)
                    if kind in ('done','error'):
                        break
            finally:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
        return StreamingResponse(frames(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.get('/api/v1/evidence/{source}/{row}', response_model=Evidence, tags=['Evidence'])
    async def evidence_row(source: str, row: int) -> Evidence:
        """场景 1.3/2.1/2.2：白名单访问原始记录，展示引用对应数据。"""
        try:
            rows = app.state.workflow.tools.rows(source)
            if row < 2 or row > len(rows) + 1:
                raise ValueError('No row')
            return rows[row - 2]
        except (ValueError, OSError):
            raise HTTPException(404, {'code': 'UNKNOWN_SOURCE_ROW', 'message': 'Evidence row not found.'})

    @app.get('/api/v1/workflow/notifications/{session_id}', tags=['Workflow'])
    async def notifications(session_id: str) -> list[dict]:
        """场景 3.3：读取已评估的站内通知；会话 ID 是本地单用户访问凭证。"""
        try:
            app.state.workflow.store.load(session_id)
        except KeyError:
            raise HTTPException(404, {'code': 'UNKNOWN_SESSION', 'message': 'Session not found.'})
        return app.state.workflow.store.notifications(session_id)

    @app.post('/api/v1/workflow/replies', tags=['Integrations'])
    async def receive_reply(body: ReplyEvent, request: Request) -> dict[str, str]:
        """场景 3.3：已认证上游回复事件入库；聊天消息不能伪造已收到回复。"""
        token = os.getenv('REPLY_INGEST_TOKEN', '')
        if not token or not secrets.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + token):
            raise HTTPException(401, {'code': 'UNAUTHORIZED', 'message': 'Integration authentication required.'})
        try:
            engine = app.state.workflow
            engine.tools.refresh_order(body.order_id)
            if body.received_at > engine.clock():
                raise ValueError('Future event')
            engine.store.record_reply(body.event_id, body.order_id, body.received_at)
        except ValueError:
            raise HTTPException(422, {'code': 'INVALID_REPLY', 'message': 'Unknown order or future event.'})
        return {'status': 'recorded'}
