# AI 后端文档入口

- [项目 README](README.md)：功能、启动、配置和运行边界。
- [后端 README](backend/README.md)：环境变量、持久化和维护命令。
- [API 文档](backend/API_DOCUMENTATION.md)：工作流、会话、确认、证据与提醒。
- [SSE 说明](backend/STREAMING_API.md)：工作流事件顺序、错误与取消语义。
- [工作流设计](docs/INTENT_WORKFLOW.md)：11 个子场景的意图、槽位、状态、工具和测试。

当前聊天页面使用 `/api/v1/workflow/chat/stream`；JSON 入口为 `/chat`。JSON 别名为 `/api/v1/workflow/chat`，所有聊天入口使用同一工作流。
