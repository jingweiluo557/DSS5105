# 前端浏览器测试

## 环境与模拟测试

以下两组测试自建本地 mock `/api/snapshot` 和 SSE 服务，不请求 OpenAI，也不要求后台启动。从项目根目录执行：

```powershell
cd tests/e2e
npm install
npm test
node verify_workspace.cjs
```

需要 Node.js、项目声明的 Playwright 依赖与 Microsoft Edge（`channel=msedge`）。安装后生成的 package-lock.json 应随团队实际版本提交。`npm test` 仅运行 `verify_stream_ui.cjs`，工作台测试需按上方命令单独运行。

snapshot.fixture.json 是测试种子，不是生产数据缓存。此测试模拟分段 SSE 以检验客户端；生产服务先验证完整答案再发送事件。

覆盖动态快照加载、增量在完成前可见、完整结果与订单上下文、停止、重试、新会话取消。后端协议另由 backend/tests/ 验证。

`verify_workspace.cjs` 额外覆盖精简导航、日报请求、连续对话的 session_id / confirmation_id、逐轮证据、会话导出、全部工具入口和移动端溢出检查。桌面与手机截图默认写入系统临时目录，可通过 `WORKSPACE_SCREENSHOT_DIR` 指定已有输出目录。两组测试使用模拟 API，不验证真实模型的回答质量。

导航断言包括侧边栏四个入口、Activity Log / Settings 的独立选中状态，以及这两个页面不显示工作台工具栏。模拟测试的固定答案只用于验证交互，不能作为真实业务结论。

## 真实接口联调

启动已配置模型和 MySQL 的后端后运行 `node verify_live_workspace.cjs`。默认访问 `http://127.0.0.1:8000`，可用 `LIVE_BASE_URL` 修改。此脚本实际调用付费模型，不拦截或模拟 API，创建真实聊天会话与备注预览，但不会确认业务写入或发送消息。结果和截图写入 Git 忽略的 `backend/runtime/live-workspace/`。模型回答存在变化，脚本失败时应检查报告中保留的响应。

先按 [项目说明](../../README.md) 启动配置好的 MySQL 和 FastAPI，再从项目根目录执行：

```powershell
cd tests/e2e
node verify_live_workspace.cjs
```

如需覆盖服务地址，PowerShell 使用 `$env:LIVE_BASE_URL='http://127.0.0.1:8001'`；POSIX shell 使用 `LIVE_BASE_URL=http://127.0.0.1:8001 node verify_live_workspace.cjs`。服务必须同源托管当前前端文件，且允许访问已配置模型。

| 测试 | 验证重点 | 不覆盖 |
|---|---|---|
| verify_stream_ui.cjs | 分段 SSE 展示、完成后卡片、停止、重试、新会话取消 | 真实模型、数据库和外部发送 |
| verify_workspace.cjs | 导航、会话字段传递、证据展示、导出、工具页面和移动端溢出 | 真实模型分类与业务规则准确性 |
| verify_live_workspace.cjs | 真实查询与追问、证据字段核对、备注预览、刷新恢复、通知读取和业务日期 | 确认落库、提醒触发、外部送达及全量业务场景 |

脚本成功退出码为 0；失败为非 0。真实测试报告保存请求、响应和失败信息，`passed: true` 表示该次脚本断言通过，不等同于所有自然语言输入或全部业务功能通过验收。报告和截图每次运行使用相同路径，需比较多次结果时先归档上一批。

运行产物可能包含业务记录和会话标识，应保留在被忽略的 runtime 目录，不提交原始报告。可提交脱敏摘要，注明时间、环境、输入、判定方式和未覆盖范围。最近一次人工核对与数据库检查见 [工作台联调报告](../../docs/reports/workspace_live_integration.md)；其中直接 SQL 核验与 SQLite 无写入检查不是浏览器脚本自身的断言。
