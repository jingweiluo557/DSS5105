"""场景 1.1–3.3：工作流 API、客户端生命周期与静态前端。"""
import asyncio
import os
import uuid
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
        app.state.client = AsyncOpenAI(api_key=key, timeout=float(os.getenv('OPENAI_TIMEOUT_SECONDS', '60')), max_retries=0) if key else None
        initialize_workflow(app, DATA, ROOT)
        monitor = asyncio.create_task(monitor_loop(app))
        try:
            yield
        finally:
            monitor.cancel()
            with suppress(asyncio.CancelledError):
                await monitor
            if app.state.client:
                await app.state.client.close()

    app = FastAPI(
        title='ThreadPilot AI API', version='1.1.0',
        description='Intent-driven, CSV-grounded workflow with persistent sessions and confirmed actions.',
        lifespan=lifespan,
        servers=[{'url': 'http://127.0.0.1:8000', 'description': 'Local development; replace with your team server when deployed'}],
    )
    app.state.client = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['http://127.0.0.1:8765', 'http://localhost:8765', 'http://127.0.0.1:8000', 'http://localhost:8000'],
        allow_methods=['GET', 'POST'], allow_headers=['Content-Type'],
    )

    @app.middleware('http')
    async def request_identity(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """场景 1.1–3.3：为每次请求添加可追踪标识。"""
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers['X-Request-ID'] = request.state.request_id
        return response

    @app.exception_handler(HTTPException)
    async def app_error(request: Request, error: HTTPException) -> JSONResponse:
        """场景 1.1–3.3：返回已定义的业务错误及请求标识。"""
        return JSONResponse(status_code=error.status_code, content={'error': {**error.detail, 'request_id': request.state.request_id}})

    @app.get('/api/v1/health', tags=['Health'])
    async def health() -> dict[str, Any]:
        """场景 1.1–3.3：查询客户端配置状态，不调用模型。"""
        return {'status': 'ok', 'configured': app.state.client is not None, 'model': os.getenv('OPENAI_MODEL', 'gpt-4.1'), 'streaming': True}

    install_workflow_routes(app, DATA)
    app.mount('/data', StaticFiles(directory=DATA), name='data')
    app.mount('/', StaticFiles(directory=FRONTEND, html=True), name='frontend')
    return app


app = create_app()
