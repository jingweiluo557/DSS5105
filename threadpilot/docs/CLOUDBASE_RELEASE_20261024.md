# CloudBase 邮件与业务时钟发布

环境：`dss5105-track1-i7gxvcy5k7ef5ac9b`，沿用现有 MySQL，禁止重新导入种子数据。

## 本次发布结果

- GitHub 分支：`codex/cloudbase-email-release-20261024`；部署代码提交 `159835eeb3f6a8d2aa60f90730d670467ed465a3`。
- 后端 `threadpilot-api` 已上传并部署；前端通过 GitHub 导入发布为 `threadpilot-007`（构建 `2600007042`）。
- 后端 ZIP SHA-256：`5e728bfb9f9128c29d5fd8181259dd45a055f9ed087bcc8aedc60115ff60e371`。
- 云端 Outlook 已连接 `jingweihyyy@outlook.com`；经理收件地址为 `1098214258@qq.com`。
- `threadpilot-email-timer` 已部署，触发器 `email-every-minute` 使用 `0 * * * * * *`；控制台测试成功返回 `briefing.status=not_due_or_claimed`、`scheduled=null`。
- 健康检查、邮箱设置、业务时钟、Activity Log、订单快照均返回 HTTP 200；现有 120 个订单、360 条生产记录、8 个车间保持可读。
- 验收时晨报处于暂停状态，未发送真实邮件，邮件 Activity Log 为 0 条。业务时钟保留原初始化值 `2026-04-01 12:00`，需在 Settings 点击 Start demo clock 开始推进，或选择 Use real time。部门邮箱尚未配置。
- 数据库升级已验证原有表数据摘要不变；备份保存在下述本地私有目录。

云端入口：https://threadpilot-dss5105-track1-i7gxvcy5k7ef5ac9b.webapps.tcloudbase.com

## 数据库

2026-10-24 已执行 `0008_ai_morning` → `0009_cloud_mail`，新增 6 张表。
原有表逐表数据摘要保持一致。私有备份与核验记录位于本地
`.build/cloudbase-migration-20261024-005402/`，不提交 Git。
后续结构升级使用 `python -m scripts.upgrade_cloud_schema --apply`；不使用 initialize 命令。

## 后端 ZIP

`dist/threadpilot-backend-python311.zip` 用于已有 HTTP 云函数 `threadpilot-api`。
Python 3.11，端口 9000，内存 1024 MB，超时 300 秒，保留公网访问。
包中包含 Linux 依赖、应用和启动入口，不含 `.env`、本地 SQLite 或 OAuth 缓存。

重建：

```powershell
uv export --project backend --locked --no-dev --no-hashes --no-emit-project -o requirements.txt
backend/.venv/Scripts/python.exe deploy/cloud-function/export_requirements.py
uv pip install --python backend/.venv/Scripts/python.exe --target .build/cloud-function-release-20261024 --python-platform x86_64-manylinux2014 --python-version 3.11 --only-binary :all: -r deploy/cloud-function/requirements-linux311.txt
backend/.venv/Scripts/python.exe deploy/cloud-function/package.py --vendor .build/cloud-function-release-20261024
```

## 环境变量

保留现有数据库、AI 和访问令牌。邮箱所需：
`OUTLOOK_CLIENT_ID`、`OUTLOOK_CLIENT_SECRET`、`OUTLOOK_ENCRYPTION_KEY`。
加密密钥必须长期保存且不随发布替换，否则已保存的邮箱状态无法解密。

```dotenv
WORKFLOW_STORAGE=database
BACKGROUND_TASKS_ENABLED=false
EMAIL_SCHEDULER_ENABLED=false
MORNING_SCHEDULER_ENABLED=false
OUTLOOK_AUTHORITY=https://login.microsoftonline.com/consumers
OUTLOOK_REDIRECT_URI=https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com/api/outlook/callback
PUBLIC_FRONTEND_ORIGIN=https://threadpilot-dss5105-track1-i7gxvcy5k7ef5ac9b.webapps.tcloudbase.com
```

Entra 中的 Web 回调必须与 OUTLOOK_REDIRECT_URI 完全一致。
前端域名须包含在 CORS_ORIGINS 中。首次部署后通过云端 Settings 重新连接 Outlook。
`/api` 网关关闭额外的跨域响应头注入，由后端统一响应 CORS；避免网关与后端重复返回 Allow-Origin/Allow-Credentials 导致浏览器拒绝响应。应用访问鉴权保持启用。
无需复制本地授权缓存。`BUSINESS_NOW` 只在尚未保存业务时钟时作为初始值；之后以 Settings 保存的时钟为准。

## Git 导入前端

| 设置 | 值 |
|---|---|
| 仓库 | jingweiluo557/DSS5105 |
| 目标目录 | threadpilot |
| 构建命令 | npm run build |
| 产物目录 | dist/frontend |
| THREADPILOT_PUBLIC_API_BASE | https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com |

分支使用本次发布分支。前端构建环境只填公开后端地址，禁止放入任何密钥。

## 分钟定时器

创建事件云函数 `threadpilot-email-timer`，上传 `dist/threadpilot-email-timer.zip`。
Python 3.11，入口 `index.main_handler`，超时 300 秒。
环境变量为 `BACKEND_ORIGIN`（上表后端地址）和现有 `SCHEDULER_TOKEN`。
配置每分钟触发，后端按照业务时钟判断是否到 07:00 或已审核邮件的发送时间。
`EMAIL_SCHEDULER_ENABLED=false` 仅关闭进程内循环，不关闭这个鉴权定时入口。
已有 reminder timer 保留；旧 morning timer 不需要与分钟邮件定时器重复启用。

## 核验

检查 `/api/v1/health`、登录后的 Settings、业务时钟和 Activity Log。
晨报自动发送要同时具备邮箱连接、收件人和已开启的晨报偏好。
部署验收不自动发送真实邮件；可由经理确认一封测试催办进行端到端验收。
