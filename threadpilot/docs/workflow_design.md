# 系统架构概览

适用版本：API 2.0.0。系统包含 Web 客户端、FastAPI 服务、MySQL 业务库和 SQLite 会话存储。

## 请求处理

1. Web 客户端通过 `/api/snapshot` 加载看板数据，通过工作流 SSE 接口发起业务对话。
2. 意图分类器提取意图与槽位；引擎合并会话状态、消解订单指代，并在存在歧义时追问。
3. 业务工具查询 MySQL 最新已提交记录，执行风险、比较、产能及异常规则，返回事实、解释与证据。
4. 发送、备注和提醒先生成预览，确认后执行；SQLite 保存会话、确认、执行记录和通知。
5. `/api/ai/ask` 使用独立 SQL 会话，通过受限 SELECT 工具查询 MySQL，并返回答案及实际查询证据。

## 数据更新

管理 API 和表格同步通过事务更新 MySQL。同步按业务键及导入哈希处理增量，冲突回滚。看板在页面刷新时获取更新，AI 工具在每轮重新读取。MySQL 与 SQLite 均需备份。

## Web 客户端结构

前端按依赖顺序加载 `app.js`、`data-views.js`、`ai-api.js`、`ai-stream.js` 和 `workspace.js`。最后一层负责展示与导航整合，复用既有对话状态和请求函数；SSE 解析、会话延续、停止、重试和确认标识仍由 `ai-stream.js` 管理。

主导航包含 Dashboard、AI workspace、Activity Log 和 Settings。订单、异常、风险、可行性及本地跟进功能放入工作台工具栏，原 hash 路由保留。Activity Log 与 Settings 是独立页面，不属于工作台工具栏。

AI 工作台将页面快照摘要、当前对话和逐轮证据放在同一页面。日报按钮提交现有聊天请求，不引入独立后端接口。Activity Log 展示浏览器本地记录，服务端执行审计仍存于 SQLite，二者不自动同步。

此导航与布局调整不改变 HTTP 方法、请求或响应字段、数据库结构和业务确认规则；API 版本保持 2.0.0。路由、存储键及模块职责见 [前端说明](../frontend/README_ZH.md)。

## 详细设计

- [意图工作流](INTENT_WORKFLOW.md)：分类体系、槽位、状态、工具、确认与业务约束。
- [数据链路](data_pipeline.md)：表结构、导入、同步、SQL 防护与迁移。
- [API 文档](../backend/API_DOCUMENTATION.md)：请求、响应、错误和 SSE 契约。
- [验证报告](live_model_verification.md)：场景覆盖、失败重跑及验证边界。
