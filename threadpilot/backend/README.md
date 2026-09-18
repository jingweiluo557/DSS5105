# ThreadPilot backend

FastAPI + OpenAI Responses SDK + Pydantic v2，使用 uv 锁定依赖。模型识别意图与槽位，Python 完成业务计算、状态更新、证据检索和写操作确认。

## 启动

在本目录运行（Python 3.12–3.13）：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 编辑 .env，填写 OPENAI_API_KEY；不要覆盖已有配置
uv sync --locked
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

也可执行 `./start.ps1`。`main:app` 是兼容启动入口，实现位于 `app/`。环境变量优先于 `.env`，修改配置后重启。

[AI 页面](http://127.0.0.1:8000/#/ai) · [Swagger](http://127.0.0.1:8000/docs) · [健康检查](http://127.0.0.1:8000/api/v1/health)

## 配置

| 环境变量 | 默认值 / 说明 |
|---|---|
| `OPENAI_API_KEY` | 无；未配置时聊天接口返回 503 |
| `OPENAI_MODEL` | `gpt-4.1`；使用支持当前结构化输出契约的模型 |
| `OPENAI_TIMEOUT_SECONDS` | `60`；共用 OpenAI 客户端超时；应用客户端不自动重试 |
| `BUSINESS_NOW` | `2026-04-01T09:00:00+08:00`；带时区固定时间用于回放；`live` 使用当前 UTC+08:00 时间 |
| `WORKFLOW_DB` | 未设置时为 `backend/runtime/workflow.sqlite3`；覆盖时建议使用绝对路径，不要设置空字符串 |
| `CHASE_WEBHOOK_URL` | 未配置则不外发；由服务端固定设置 |
| `CHASE_WEBHOOK_TOKEN` | 发送网关 Bearer token |
| `REPLY_INGEST_TOKEN` | 回复事件接入 Bearer token；未配置则拒绝接入 |

正式业务数据来自 `../data/` 的三份 CSV。没有自动接入工厂实时系统；`BUSINESS_NOW=live` 不会更新 CSV。默认回放时钟冻结，提醒不会因墙钟经过而到期。

## 接口选择

| 接口 | 用途 |
|---|---|
| `POST /chat` 或 `/api/v1/workflow/chat` | 有状态工作流 JSON |
| `POST /api/v1/workflow/chat/stream` | 当前网页使用；验证完成后发送 SSE |
| `GET /api/v1/evidence/{source}/{row}` | 原始 CSV 行证据 |
| `GET /api/v1/workflow/notifications/{session_id}` | 已生成的条件提醒通知 |
| `POST /api/v1/workflow/replies` | 已认证上游记录真实回复事件 |

首轮不传 `session_id`，后续使用响应 `state.session_id`。客户端不能上传可信状态、意图或工具指令。发送/保存/创建提醒需先预览，再用确认文本与 `confirmation_id` 确认。

完整字段、错误、确认、发送网关与示例见 [API 文档](API_DOCUMENTATION.md)；流式协议见 [STREAMING_API.md](STREAMING_API.md)。

## 实现位置

- `app/main.py`：应用、客户端生命周期、静态资源与健康检查。
- `app/schemas.py`：Intent、Slots、DialogState、ToolCall、请求响应模型。
- `app/intent_classifier.py`：独立 `SYSTEM_PROMPT` 和结构化分类。
- `app/workflow_engine.py`：意图路由、实体澄清、状态更新、确认门禁。
- `app/workflow_tools.py`：刷新 CSV、风险与排序、产能、同 weekday 基线和原始证据。
- `app/workflow_store.py`：SQLite 会话/审计、内部备注、提醒、通知、回复事件和发送适配器。
- `app/workflow_api.py`：新路由与提醒检查循环。

完整业务设计见 [Intent Workflow](../docs/INTENT_WORKFLOW.md)。

## 持久化与持续运行

`runtime/` 已被 Git 忽略且不作为静态资源公开。SQLite 保存会话、已确认操作、提醒、回复事件及通知；备份和迁移时保留数据库。前端“新会话”丢弃客户端当前会话 ID，不代表删除服务端记录。

后端按约 30 秒间隔检查到期提醒，检查与聊天共用进程锁，繁忙时可能延后。条件满足则静默，未满足则生成站内通知；网页约每 30 秒读取通知。服务关闭期间不执行检查，重启后补检。`no_reply` 依赖真实回复接入；缺少接入时只能判断“系统未记录回复”。

只运行 **一个 worker**。当前没有用户登录和跨进程并发保护；随机会话 ID 是本地访问凭证。外发依赖支持 `Idempotency-Key` 的网关，未配置时返回 `not_sent`，无法确定送达时返回 `unknown`，不会谎报成功。

## 验证与维护

```powershell
# 离线回归：不调用真实模型
uv run --locked pytest -q
# 接口改变后导出并提交 OpenAPI
uv run --locked python -m scripts.export_openapi
# 正式 CSV 改变后更新前端快照
uv run --locked python -m scripts.build_frontend_data
# 可选真实工作流评测：消耗 API 额度；消息发送用测试替身
uv run --locked python -m scripts.evaluate_workflow
```

真实评测报告保存在 `runtime/live-evaluation.json`。`scripts.smoke_live` 使用 TestClient 测试 `/chat`，`scripts.smoke_stream` 测试运行中服务的工作流 SSE；两者均调用真实模型，只进行订单查询，不执行业务写操作。完整多轮覆盖使用 evaluate_workflow。

[项目 README](../README.md) · [OpenAPI 文件](../docs/openapi.json) · [前端回归](../tests/e2e/README.md)
