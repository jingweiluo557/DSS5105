# ThreadPilot

Track 1 apparel management cockpit and AI Co-Pilot。英文界面，FastAPI + OpenAI 流式回答，uv 管理后端。

## 启动

在项目根目录打开 PowerShell：

```powershell
cd backend
# 仅首次克隆且没有 .env 时复制；不要覆盖已有配置
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 编辑 .env，填写 OPENAI_API_KEY
uv sync --locked
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

[AI 页面](http://127.0.0.1:8000/#/ai) · [驾驶舱](http://127.0.0.1:8000/#/dashboard) · [Swagger](http://127.0.0.1:8000/docs) · [健康检查](http://127.0.0.1:8000/api/v1/health)

目录迁移或配置变更后，在旧服务终端按 Ctrl+C，再运行新命令。backend/.env 和 .venv 已保留，不需要再启动 8765。

## 目录结构

```text
threadpilot-v2/
├── frontend/                 # HTML、CSS、JS 与本地图片
│   ├── index.html
│   ├── app.js                # 导航和状态
│   ├── data-views.js          # 数据页面
│   ├── ai-api.js              # 聊天渲染和上下文
│   ├── ai-stream.js           # SSE、停止和重试
│   └── data.js                # CSV 生成的快照
├── backend/                  # uv 项目
│   ├── app/                  # 应用实现
│   ├── tests/                # 离线接口测试
│   ├── scripts/              # 维护与手动联调
│   ├── main.py               # 旧启动入口兼容
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .env.example
│   └── API_DOCUMENTATION.md  # 完整接口契约
├── data/                     # 源 CSV 与数据字典
├── docs/                     # 手册、OpenAPI、迁移和请求示例
├── tests/e2e/                # 前端流式交互测试
├── archive/                  # 历史设计稿、Stitch 导出和旧工具
├── .gitignore
└── CONTRIBUTING.md
```

## 文档与验证

- [流式接口与完整链接](backend/API_DOCUMENTATION.md)
- [OpenAPI 导入文件](docs/openapi.json)
- [操作手册](docs/USER_MANUAL.md)
- [团队协作流程](CONTRIBUTING.md)
- [目录迁移映射](docs/MIGRATION.md)
- [前端交互测试](tests/e2e/README.md)

在 backend 执行：

```powershell
uv run --locked pytest -q
uv run --locked python -m scripts.export_openapi
uv run --locked python -m scripts.build_frontend_data
```

测试使用 mock，不消耗 API 额度。后两条更新 docs/openapi.json 与 frontend/data.js，在接口或 CSV 改动后生成并提交。

## 当前边界

数据是业务日期 2026-04-01 的课程快照。真实 AI 需要有效配置、网络和额度。备注、监控、回执只存在当前浏览器；真实外发、语音识别、定时任务和跨设备同步尚未实现。

GitHub 存储代码与文档，127.0.0.1 指向每位成员自己的电脑。不要提交 .env、.venv 或真实密钥。
