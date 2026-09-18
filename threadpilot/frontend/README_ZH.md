# ThreadPilot 前端

原生 HTML / CSS / JS，由 FastAPI 托管：[AI 页面](http://127.0.0.1:8000/#/ai)。

加载顺序：data.js → app.js → data-views.js → ai-api.js → ai-stream.js。
app.js 提供页面与状态，data-views.js 提供数据视图，ai-api.js 仅提供共用聊天渲染和状态交互，ai-stream.js 接管流式请求、停止和重试。

当前请求入口为 `POST /api/v1/workflow/chat/stream`，使用服务端 `session_id` 延续对话并携带 `confirmation_id` 确认预览。新接口在规则验证完成后返回 SSE，不是实时模型 token 增量。前端展示逐行证据链接，并约每 30 秒读取当前会话的条件提醒通知。

会话 ID 保存在 sessionStorage；“新会话”清除客户端关联，不删除后端数据库。停止读取不保证撤销已经确认的业务操作。原驾驶舱的本地备注、Watch 和模拟发送与聊天工作流的 SQLite 记录独立存在。

CSV 的维护位置是根目录 data/。修改后在 backend 执行：
`uv run --locked python -m scripts.build_frontend_data`，提交生成的 frontend/data.js。

开发统一使用 8000，无需另外启动静态服务。参见 [项目说明](../README.md) 和 [接口文档](../backend/API_DOCUMENTATION.md)。

