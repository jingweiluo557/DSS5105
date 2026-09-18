# ThreadPilot

面向服装工厂订单与运营管理的 AI Co-pilot。英文业务界面，使用 **FastAPI + OpenAI Python SDK + Pydantic v2**，通过意图识别驱动查询、分析、人工确认和条件监控。后端由 uv 管理。

## 功能

| 场景 | 支持能力 |
|---|---|
| 订单与客户管理 | 模糊订单澄清、活动订单刷新、可解释风险、并排比较、新订单产能估算、每日异常排序 |
| 工厂运营 | 同 weekday 产出对照、生产偏差与共现事实解释、原始记录证据 |
| 执行与监控 | 催办草稿与修订、确认后调用发送网关、内部备注、条件提醒与原位更新 |

模型负责结构化意图和槽位识别，Python 执行查询、计算与确认规则。多候选订单不会自动选择第一条；事实与预测分别展示；业务写操作先预览、再确认。回答包含原始 CSV 行及证据链接。

## 快速启动

需要 Python 3.12–3.13 和 uv。在项目根目录打开 PowerShell：

```powershell
cd backend
# 仅首次创建；不要覆盖已有配置
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 编辑 .env，填写 OPENAI_API_KEY
uv sync --locked
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

也可执行 `backend/start.ps1`。配置变更后重启服务。前后端由同一个 FastAPI 服务托管，无需额外启动 8765 静态服务。

[AI 页面](http://127.0.0.1:8000/#/ai) · [驾驶舱](http://127.0.0.1:8000/#/dashboard) · [Swagger](http://127.0.0.1:8000/docs) · [健康检查](http://127.0.0.1:8000/api/v1/health)

新 JSON 入口为 `POST /chat`（等价于 `/api/v1/workflow/chat`），网页使用 `/api/v1/workflow/chat/stream`。首轮只需 `{"message":"Show me the TrendCart order."}`；后续传回响应中的 `state.session_id`，由服务端恢复上下文。完整示例见 [API 文档](backend/API_DOCUMENTATION.md)。

## 配置与数据

配置保存在 `backend/.env`，模板见 [backend/.env.example](backend/.env.example)。已存在的同名进程环境变量优先。

| 配置 | 用途 |
|---|---|
| `OPENAI_API_KEY` / `OPENAI_MODEL` | 服务端模型凭证与模型；默认 `gpt-4.1` |
| `BUSINESS_NOW` | 默认冻结为 `2026-04-01T09:00:00+08:00`，用于复现正式数据；实际运行时钟使用 `live` |
| `WORKFLOW_DB` | 可选 SQLite 路径；不设置时为 `backend/runtime/workflow.sqlite3` |
| `CHASE_WEBHOOK_URL` / `CHASE_WEBHOOK_TOKEN` | 真实消息发送网关；未配置时明确返回未发送 |
| `REPLY_INGEST_TOKEN` | 上游真实回复事件的接入凭证，用于判断 no_reply 条件 |

正式事实来源为 `data/orders.csv`、`data/production_log.csv`、`data/workshops.csv`。`data/dialogs.xlsx` 提供场景与对话要求，其示例输出不是事实来源。数据字典的业务日期是 2026-04-01，产量日志截至 2026-03-31；没有订单事件明细、blocker 或工厂实时连接。

工作流每次查询重新读取 CSV。修改 CSV 后，还需重建 `frontend/data.js`，才能更新驾驶舱的数据快照。把 `BUSINESS_NOW` 改为 `live` 只改变时钟，不会自动更新业务数据。

## 目录结构

```text
threadpilot/
├── frontend/                    # 原生 HTML/CSS/JS、驾驶舱和 AI 页面
│   ├── ai-api.js                # 聊天渲染、状态与页面交互
│   ├── ai-stream.js             # 当前工作流 SSE、会话、证据、通知
│   └── data.js                  # 从 CSV 生成的页面快照
├── backend/
│   ├── app/
│   │   ├── main.py              # 应用生命周期、静态服务与健康检查
│   │   ├── schemas.py           # Intent、Slots、DialogState、ToolCall
│   │   ├── intent_classifier.py # 独立 system prompt、结构化意图输出
│   │   ├── workflow_engine.py   # 路由、状态、确认与回复
│   │   ├── workflow_tools.py    # 数据刷新、证据和确定性计算
│   │   ├── workflow_store.py    # SQLite、发送网关、审计与提醒
│   │   └── workflow_api.py      # 新工作流、证据、通知与回复接入
│   ├── runtime/                # 私有数据库、评测报告；不提交 Git
│   ├── tests/                  # 场景、接口和边界回归
│   ├── scripts/                # OpenAPI 导出、快照生成、真实模型评测
│   ├── pyproject.toml
│   └── uv.lock
├── data/                       # 正式数据、数据字典和对话场景表
├── docs/                       # 工作流设计、OpenAPI、请求示例
└── tests/e2e/                  # Edge/Playwright 前端回归
```

## 文档与验证

- [后端配置和维护](backend/README.md)
- [API 文档与联调示例](backend/API_DOCUMENTATION.md)
- [工作流 SSE 协议](backend/STREAMING_API.md)
- [意图、槽位、状态、工具与计算规则](docs/INTENT_WORKFLOW.md)
- [OpenAPI 定义](docs/openapi.json)
- [前端说明](frontend/README_ZH.md) · [浏览器测试](tests/e2e/README.md)
- [原驾驶舱操作手册](docs/USER_MANUAL.md)（其中浏览器模拟操作与新聊天工作流须区分）
- [团队协作约定](CONTRIBUTING.md)

在 `backend` 目录执行：

```powershell
uv run --locked pytest -q
uv run --locked python -m scripts.export_openapi
# 仅在 CSV 变化后更新页面快照
uv run --locked python -m scripts.build_frontend_data
# 可选：真实模型评测，消耗 API 额度，业务发送使用测试替身
uv run --locked python -m scripts.evaluate_workflow
```

工作流曾完成 11 个子场景共 45/45 轮真实模型评测；离线与浏览器回归按当前代码运行。该记录是一次场景验证结果，不是任意输入的准确率保证；详见 [设计与验证说明](docs/INTENT_WORKFLOW.md)。

## 运行边界

- 新聊天工作流的会话、确认后内部备注、提醒和发送审计存入服务端 SQLite；原驾驶舱的部分本地备注、Watch、设置和模拟外发流程仍独立存在，不会自动同步到工作流。
- 条件提醒由运行中的后端周期检查，网页读取站内通知。默认冻结时钟不会自然走到“明天”；持续监控需 `BUSINESS_NOW=live`、更新中的数据/回复事件，并保持服务运行。服务重启后补检到期提醒。
- 真实发送需要可验证回执且支持幂等键的网关；起草、确认请求及网络超时均不等于已经送达。
- 当前是本地单用户原型，使用单个 Uvicorn worker。尚无登录、会话归属鉴权或分布式锁；多用户部署需要补齐这些能力。请把随机会话 ID 视为访问凭证。
- 聊天统一使用 `/chat`、`/api/v1/workflow/chat` 或 `/api/v1/workflow/chat/stream`，共享服务端状态和确认规则。

GitHub 存储代码和文档；`127.0.0.1` 指向运行服务的本机。不要提交 `.env`、`.venv`、运行时数据库或真实密钥。
