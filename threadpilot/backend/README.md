# ThreadPilot backend

FastAPI + OpenAI Responses，uv 管理。配置为本目录 .env，参考 [.env.example](.env.example)。

```powershell
uv sync --locked
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

也可运行 start.ps1。main:app 是兼容入口，新实现位于 app/。.env 与 .venv 保留原位置。

[接口文档](API_DOCUMENTATION.md) · [项目说明](../README.md) · [AI 页面](http://127.0.0.1:8000/#/ai) · [Swagger](http://127.0.0.1:8000/docs)

- 离线验证：`uv run --locked pytest -q`
- 导出契约：`uv run --locked python -m scripts.export_openapi`
- 重建前端数据：`uv run --locked python -m scripts.build_frontend_data`
- 真实流式测试：`uv run --locked python -m scripts.smoke_stream`（先启动服务，会消耗 API 额度）
- 真实非流式测试：`uv run --locked python -m scripts.smoke_live`
