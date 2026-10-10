"""场景 1.1–3.3：工作流 API、客户端生命周期与静态前端。"""
import asyncio
import os
import uuid
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI

from .workflow_api import initialize_workflow, install_workflow_routes, monitor_loop
from .config import Settings
from .db.session import Database
from .services.sync_service import SyncService
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT.parent / 'frontend'
DATA = ROOT.parent / 'data'
load_dotenv(ROOT / '.env', override=False)


def create_app() -> FastAPI:
    """场景 1.1–3.3：仅注册意图工作流及其证据、通知与集成接口。"""
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """场景 1.1–3.3：共用模型客户端并管理已确认提醒的检查任务。"""
        key = os.getenv('OPENAI_API_KEY', '').strip()
        app.state.settings = Settings()
        app.state.database = Database(app.state.settings)
        app.state.sql_agent = None
        app.state.sync = SyncService(app.state.database, app.state.settings)
        if app.state.settings.background_tasks_enabled:
            app.state.sync.start()
        app.state.client = AsyncOpenAI(api_key=key, base_url=app.state.settings.openai_base_url, timeout=app.state.settings.openai_timeout_seconds, max_retries=0) if key else None
        initialize_workflow(app, DATA, ROOT)
        monitor = asyncio.create_task(monitor_loop(app)) if app.state.settings.background_tasks_enabled else None
        from .api.dashboard_api import morning_loop
        morning = asyncio.create_task(morning_loop(app)) if app.state.settings.morning_scheduler_enabled else None
        try:
            yield
        finally:
            if morning:
                morning.cancel()
                with suppress(asyncio.CancelledError):
                    await morning
            if monitor:
                monitor.cancel()
                with suppress(asyncio.CancelledError):
                    await monitor
            if app.state.client:
                await app.state.client.close()
            app.state.sync.close()
            if app.state.sql_agent:
                app.state.sql_agent.close()
            app.state.database.close()

    app = FastAPI(
        title='ThreadPilot AI API', version='2.0.0',
        description='MySQL-grounded intent workflow, incremental synchronization and read-only SQL Agent.',
        lifespan=lifespan,
        servers=[{'url': 'http://127.0.0.1:8000', 'description': 'Local development; replace with your team server when deployed'}],
    )
    app.state.client = None
    @app.middleware('http')
    async def request_identity(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """场景 1.1–3.3：为每次请求添加可追踪标识。"""
        request.state.request_id = str(uuid.uuid4())
        settings = getattr(app.state, 'settings', None)
        token = settings.api_access_token.get_secret_value() if settings else ''
        protected = request.url.path == '/chat' or request.url.path.startswith('/api/')
        exempt = request.url.path in ('/api/v1/health', '/api/internal/reminders/run', '/api/internal/briefings/run', '/api/v1/workflow/replies')
        if token and protected and not exempt and request.method != 'OPTIONS':
            supplied = request.headers.get('X-ThreadPilot-Token', '')
            if not secrets.compare_digest(supplied.encode(), token.encode()):
                return JSONResponse(status_code=401, content={'error': {'code': 'UNAUTHORIZED', 'message': 'Application access token required.'}})
        response = await call_next(request)
        response.headers['X-Request-ID'] = request.state.request_id
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=Settings().cors_origins,
        allow_methods=['GET', 'POST', 'PUT', 'DELETE'], allow_headers=['Content-Type', 'Authorization', 'X-Confirm-Write', 'X-ThreadPilot-Token'],
    )

    @app.exception_handler(HTTPException)
    async def app_error(request: Request, error: HTTPException) -> JSONResponse:
        """场景 1.1–3.3：返回已定义的业务错误及请求标识。"""
        detail = error.detail if isinstance(error.detail, dict) else {'code': 'HTTP_ERROR', 'message': str(error.detail)}
        return JSONResponse(status_code=error.status_code, content={'error': {**detail, 'request_id': request.state.request_id}})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        """场景 1.2：数据库错误不泄露连接字符串或 SQL 参数。"""
        conflict = isinstance(error, IntegrityError)
        return JSONResponse(status_code=409 if conflict else 503, content={'error': {'code': 'DATA_CONFLICT' if conflict else 'DATABASE_UNAVAILABLE', 'message': 'Duplicate/inconsistent record.' if conflict else 'Check database connectivity and run migrations.'}})

    @app.exception_handler(ValueError)
    async def invalid_data(request: Request, error: ValueError) -> JSONResponse:
        """场景 1.2：返回导入校验错误，避免输出上传的原始值。"""
        from .services.importer import ImportConflict
        message = 'Invalid data fields/types; check the data dictionary.' if isinstance(error, ValidationError) else str(error)[:300]
        return JSONResponse(status_code=409 if isinstance(error, ImportConflict) else 422, content={'error': {'code': 'IMPORT_CONFLICT' if isinstance(error, ImportConflict) else 'INVALID_DATA', 'message': message}})

    @app.get('/api/v1/health', tags=['Health'])
    async def health() -> dict[str, Any]:
        """场景 1.1–3.3：查询客户端配置状态，不调用模型。"""
        return {'status': 'ok', 'configured': app.state.client is not None, 'model': os.getenv('OPENAI_MODEL', 'gpt-4.1'), 'streaming': True}

    install_workflow_routes(app, DATA)
    from .api import data_api, sync_api, snapshot_api, ai_api, dashboard_api
    for router in (data_api.router, sync_api.router, snapshot_api.router, ai_api.router, dashboard_api.router):
        app.include_router(router)
    if Settings().serve_frontend:
        app.mount('/', StaticFiles(directory=FRONTEND, html=True), name='frontend')
    return app


app = create_app()
