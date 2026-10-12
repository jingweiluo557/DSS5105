# 本次 CloudBase 更新指南（2026-10-10）

Git 仓库：`https://github.com/jingweiluo557/DSS5105`
发布分支：`codex/dashboard-forecast-email`
环境：`dss5105-track1-i7gxvcy5k7ef5ac9b`（新加坡）

本指南用于当前 HTTP 云函数 + 静态网站托管架构，优先于早期文档中的云托管和 SQLite 说明。

## 1. 更新后端（先做）

1. CloudBase → 云函数 → 选择 HTTP 网关 `/api` 当前关联的完整后端函数。
2. 函数代码 → 上传代码，选择本机 `dist/threadpilot-backend-python311.zip`，点击部署。不要上传仓库源码 ZIP 或整个项目目录。
3. 保留 Python 3.11、监听端口 9000；建议内存 1024 MB、执行超时 120 秒，开启公网访问。ZIP 已含 Linux 依赖和启动文件，不用填写普通云函数的执行方法。
4. 保留云端原有数据库、AI、API_ACCESS_TOKEN 和 SCHEDULER_TOKEN 等私密配置。确认 `BACKGROUND_TASKS_ENABLED=false`、`MORNING_SCHEDULER_ENABLED=false`、`SYNC_ENABLED=false`；云端使用独立定时函数。业务演示继续 `BUSINESS_NOW=2026-04-01T12:00:00+08:00`。
5. HTTP 网关 `/api` 路由关联该函数，开启路径透传；例如 `/api/dashboard` 必须完整传给后端。现有前端使用应用访问令牌，保留其鉴权方式。
6. 打开后端 `/api/v1/health` 检查启动；该检查不代表数据库及 AI 调用全部正常，部署前端后继续验证各页面。

此环境数据库迁移 0003–0005 和 34 条预测已完成，无需重新初始化或导入。新环境才需要迁移与导入步骤。邮件草稿表为 `briefing_email_drafts`。

## 2. 从 Git 部署前端

CloudBase → 静态网站托管 → 更新现有应用的 Git 配置，或首次选择 Git 个人仓库部署。

| 字段 | 填写 |
|---|---|
| 仓库 | jingweiluo557/DSS5105 |
| 分支 | codex/dashboard-forecast-email |
| 框架 | 纯静态 / 其他（HTML、CSS、JavaScript） |
| 项目根目录（若有） | threadpilot/frontend |
| 安装命令 | 留空；必填时填 `echo No dependencies` |
| 构建命令 | 留空；必填时填 `echo Static site ready` |
| 输出目录 | 若根目录已选 threadpilot/frontend，填 `.`；若没有根目录选项且基于仓库根构建，填 `threadpilot/frontend` |
| 部署路径 | `/`（更新现有站点使用原路径） |

不要选择 React/Vue 模板，也不需要 npm install。上传产物根部应直接包含 index.html、config.js、dashboard.js、assets 等文件。

前端 config.js 已指向现有 CloudBase 后端 HTTPS 域名。这里不能填写数据库密码、模型密钥或服务端令牌。

## 3. 跨域配置

部署后复制实际前端网址，仅取协议与域名（origin，不带 `/#/dashboard` 或路径）。

在 HTTP 后端环境变量 `CORS_ORIGINS` 中加入这个 origin，保留仍在使用的前端域名。格式为 JSON 数组，如 `["https://你的实际前端域名"]`；可视化输入不要额外套单引号。网关启用跨域时，也允许该 origin、OPTIONS 和应用访问令牌请求头 `X-ThreadPilot-Token`，避免两层返回冲突的跨域响应头。

若网站与 API 实际同源则不需要新增跨域 origin。首次打开网站按提示输入现有工作区访问令牌；不要填 AI Key 或数据库密码。

## 4. 每天 07:00 的日报（未配置时需要做）

1. 新建或更新普通云函数 `threadpilot-morning-timer`，Python 3.11，上传本机 `dist/threadpilot-morning-timer.zip`。
2. 执行方法填 `index.main_handler`，开启公网访问，超时 120 秒。
3. `BACKEND_ORIGIN` 填后端 HTTPS origin（无 `/api` 后缀）；`SCHEDULER_TOKEN` 与 HTTP 后端相同。
4. 添加每日 UTC+8 07:00 定时触发。七段 Cron：控制台采用 UTC+8 时用 `0 0 7 * * * *`；明确采用 UTC 时用 `0 0 23 * * * *`。以控制台下一次触发时间为准。
5. 07:00 后手动测试应得到 completed 或 already_saved。现有 reminder timer 继续保留，和 morning timer 用途不同。

邮件按钮按需生成可编辑草稿；每天自动归档日报不会自动发送邮件。

## 5. 验收与回退

- 强制刷新前端：确认卡片折线、AI predictions、待办、日报邮件按钮存在，Orders 顶部说明条已移除。
- 保存一个邮件草稿，刷新后重新打开，验证数据库持久化。
- 使用已有正常提问检查 AI 回答；检查云函数日志无启动、数据库和跨域错误。
- Git 推送本身不代表 CloudBase 已发布；确认控制台显示本次分支的提交。
- 保留旧云函数版本及静态部署记录，异常时回到上一版代码。新增数据库表可保留，无需删除现有业务数据。

官方参考：
- https://docs.cloudbase.net/hosting/web-hosting
- https://docs.cloudbase.net/hosting/web-hosting-static
- https://docs.cloudbase.net/cloud-function/quickstart/httpfunc/python
- https://docs.cloudbase.net/cloud-function/timer-trigger
