# CloudBase 邮件与业务时钟发布

环境：`dss5105-track1-i7gxvcy5k7ef5ac9b`，沿用现有 MySQL，禁止重新导入种子数据。

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
