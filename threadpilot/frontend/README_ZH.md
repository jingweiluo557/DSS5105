# ThreadPilot 前端

原生 HTML / CSS / JS，由 FastAPI 托管：[AI 页面](http://127.0.0.1:8000/#/ai)。

加载顺序：data.js → app.js → data-views.js → ai-api.js → ai-stream.js。
app.js 提供页面与状态，data-views.js 提供数据视图，ai-api.js 提供聊天渲染和上下文，ai-stream.js 接管流式请求、停止和重试。

CSV 的维护位置是根目录 data/。修改后在 backend 执行：
`uv run --locked python -m scripts.build_frontend_data`，提交生成的 frontend/data.js。

开发统一使用 8000，无需另外启动静态服务。参见 [项目说明](../README.md) 和 [接口文档](../backend/API_DOCUMENTATION.md)。

