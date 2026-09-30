# ThreadPilot 前端说明

适用版本：API 2.0.0。前端使用原生 HTML、CSS 和 JavaScript，由 FastAPI 同源托管。启动步骤见 [项目说明](../README.md)，操作说明见 [用户手册](../docs/USER_MANUAL.md)。

## 数据加载与模块职责

`data.js` 请求 `/api/snapshot`，取得 MySQL 数据后按顺序加载 `app.js` → `data-views.js` → `ai-api.js` → `ai-stream.js` → `workspace.js`。数据库为空或请求失败时显示错误，页面不能通过双击 HTML 独立运行。模块共享全局状态且存在函数覆盖依赖，不能调整为并行加载。

| 模块 | 职责 |
|---|---|
| data.js | 加载数据库快照并启动页面 |
| app.js | 页面导航、状态和本地交互 |
| data-views.js | 订单、产出及外协厂数据视图 |
| ai-api.js | 聊天渲染和共用状态交互 |
| ai-stream.js | SSE 请求、停止、重试和会话切换 |
| workspace.js | 侧边栏与工作台工具导航、三栏布局、逐轮证据、对话定位和导出 |
| styles.css | 基础页面样式与工作台响应式样式 |

看板使用页面加载时的快照，刷新页面可获取更新。数据维护通过管理 API 或表格导入完成；AI 每轮独立读取数据库。`scripts.gen_snapshot` 和 `scripts.build_frontend_data` 仅导出离线 JSON，不生成或覆盖 `frontend/data.js`。

## 导航与路由

前端使用 hash 路由；刷新页面和直接访问下列地址均由同一静态入口加载。

| 入口 | 路由 | 页面范围 |
|---|---|---|
| 品牌标识 / 封面 | `#/cover` | 封面；进入 Dashboard |
| 侧边栏 Dashboard | `#/dashboard` | 数据快照、指标与生产趋势 |
| 侧边栏 AI workspace | `#/ai` | 对话、日报入口、当前对话记录与证据 |
| 侧边栏 Activity Log | `#/activity` | 浏览器本地操作日志、筛选与 JSON 导出 |
| 侧边栏 Settings | `#/settings` | 本地偏好、数据说明与本地状态重置 |
| 工作台工具栏 | `#/orders`、`#/exceptions`、`#/risk`、`#/feasibility`、`#/messages` | 订单、异常、风险、可行性、Watches & receipts |

`#/order?id=…`、`#/evidence?id=…`、`#/draft?id=…` 和 `#/result` 保留原有详情与结果路由。订单查询参数、筛选和旧深链接继续有效。

Activity Log 与 Settings 页面各自高亮侧边栏入口，不显示工作台工具栏；订单等工作台子页高亮 AI workspace。移动端通过菜单按钮展开侧边栏。Ask AI 入口跳转到统一对话页，使用现有会话。

## 聊天与证据

界面主导航为 Dashboard、AI workspace、Activity Log 和 Settings，封面与 Dashboard 保留原有展示。AI 工作台采用日报／当前对话记录、对话、逐轮数据库证据三栏布局，窄屏优先显示对话。订单、异常、风险、可行性和提醒从工作台工具栏进入；活动日志与设置从侧边栏进入，原有深链接仍然可用。

`workspace.js` 在原有模块之后加载，仅调整展示与入口，不修改 `ai-stream.js` 的请求、SSE 解析、会话和确认流程。日报按钮复用当前对话接口，允许后端继续追问；左侧摘要来自页面加载时的数据库快照。对话记录支持定位与 JSON 导出，范围为当前浏览器标签页会话，新会话沿用原有清空行为。每轮回答的证据链接按后端返回的记录展示。

聊天入口为 `POST /api/v1/workflow/chat/stream`。客户端使用服务端返回的 `session_id` 延续对话，使用 `confirmation_id` 确认操作预览。服务端完成规则验证后发送 SSE，答案不是模型 token 的实时增量。前端显示记录证据链接，并约每 30 秒读取会话的条件提醒通知。

会话 ID 存放于 sessionStorage。“新会话”切换客户端上下文，不删除服务端记录。停止读取不撤销已确认的业务操作；确认重试须使用同一会话及确认 ID。完整契约见 [API 文档](../backend/API_DOCUMENTATION.md)。

### 数据与状态边界

| 内容 | 来源与更新方式 | 限制 |
|---|---|---|
| Dashboard、工作台左侧摘要 | 页面加载时的 `/api/snapshot` | 刷新页面才重新获取；业务日期与生产记录日期分别展示 |
| 日报按钮 | 通过同一 `ask()` 提交业务问题 | 无独立日报接口；现有工作流可追问时间范围，生产分析通过后续提问完成 |
| 对话记录 | `threadpilot-llm-chat`，存于 sessionStorage | 当前标签页记录；支持定位和导出，不提供服务端历史会话列表 |
| 工作流会话标识 | `threadpilot-workflow-session`，存于 sessionStorage | 刷新后续用；New conversation 清除客户端会话标识 |
| 待确认操作标识 | `ai-stream.js` 内存中的 confirmation_id | 不单独持久化；刷新后可能需要重新请求预览 |
| Actual evidence | 每轮完成响应的 evidence | 仅展示 orders / production_log / workshops 的稳定记录链接；点击读取当前数据库记录 |
| Activity Log 与设置 | `threadpilot-track1-v2`，存于 localStorage | 浏览器本地操作；不是服务端执行审计或数据库同步日志 |

证据路径为 `/api/evidence/{dataset}/{record_id}`；record_id 是数据库主键，不是 CSV 行号。原始响应包含当时查询到的记录，链接返回访问时的当前值，不能作为不可变历史快照。会话导出包含当前客户端保存的消息和证据，不是完整服务端会话备份；不支持导入恢复。

## 本地功能与服务端操作

订单页本地备注、Watch、模拟发送和设置偏好使用浏览器存储，不同步为 MySQL 业务数据或 SQLite 工作流记录。模拟发送不产生外部消息。服务端备注、催办和提醒通过聊天工作流执行，且需要预览和显式确认。

开发默认通过 FastAPI 的 8000 端口访问，无需独立静态服务。浏览器测试及覆盖范围见 [端到端测试说明](../tests/e2e/README.md)。
