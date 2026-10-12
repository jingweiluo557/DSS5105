# ThreadPilot 完整 HTTP 云函数后端

适用环境：`dss5105-track1-i7gxvcy5k7ef5ac9b`，新加坡，Python 3.11。
这是完整 FastAPI 后端，替代之前仅检查数据库和模型的 `threadpilot-api-test` 探针。

## 已完成

- 工作流 JSON / SSE、只读 SQL Agent、业务数据查询、导入及确认写入接口。
- MySQL 持久化对话、待确认操作、操作记录、提醒、回复、通知和 SQL 问答历史。
- MySQL 会话锁防止多个函数实例同时修改同一会话；重复提醒通过唯一键去重。
- 停用实例内后台任务，提醒由独立定时函数触发；连接池限制为每个池 2 + 2 个连接。
- 前端访问令牌、管理写入令牌、定时任务令牌分离。代码包不包含密码、密钥或前端文件。
- 云端迁移版本 `0002` 已执行，原演示数据保持 120 / 360 / 8 条。

## 上传主函数

在「云函数」创建 `threadpilot-api`，或更新现有 Python 3.11 HTTP 测试函数。

| 设置 | 值 |
|---|---|
| 函数类型 | HTTP 云函数 |
| 代码 | `dist/threadpilot-backend-python311.zip`，直接上传 ZIP |
| 运行环境 | Python 3.11 |
| 监听端口 | 9000 |
| 内存 | 建议 1024 MB 起步，按实际监控调整 |
| 执行超时 | 建议 300 秒；若套餐限制更低，以控制台可选值为准 |
| 公网访问 | 开启，连接 MySQL 公网入口和模型服务 |
| VPC | 当前使用已验证的公网连接，不需要开启 |
| API Key 注入 | 当前实现不调用 CloudBase SDK，无需开启 |
| 环境变量 | 在 JSON 输入中粘贴本机 `backend/.env.cloudfunction.json` 的完整内容 |

配置 JSON 含密钥，仅用于控制台。不要上传到 Git 或发到聊天。
JSON 的语法双引号是必要的，控制台「可视化输入」显示的值不应带额外外层引号。
启动脚本固定监听 9000，不再使用之前误设为带引号的 8000 端口。

主函数不在启动时建表，不导入演示数据。未来更新数据库结构须显式运行迁移。

## HTTP 网关

默认域名：
`dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com`

添加或调整路由 `/api`，资源选完整后端函数，开启路径透传。
网关身份认证保持关闭，由后端验证访问令牌。需要跨域时开启跨域设置并配置实际前端域名。
如果保留 `/` 路由用于后端联调，也必须指向完整函数；后续托管前端时保留 `/api` 给后端。
`/chat` 是兼容别名，前端应使用 `/api/v1/workflow/chat`。

首次访问 `https://上述域名/api/v1/health` 应返回 `status: ok`。
其他普通业务接口需要请求头 `X-ThreadPilot-Token: <API_ACCESS_TOKEN>`。
管理写入接口还需要原来的 `Authorization: Bearer <DATA_API_TOKEN>` 及接口要求的确认头。
令牌不能直接写入公开前端源码；前端仍需接入令牌输入/会话管理，然后才能使用这些受保护接口。
当前是共享访问令牌的团队演示模式，不包含独立用户账户和租户隔离。

若前端使用另一个域名，同时修改函数 `CORS_ORIGINS` 和网关跨域白名单。
`CORS_ORIGINS` 是 JSON 数组字符串，例如 `["https://你的前端域名"]`，不包含路径。
配置文件目前保留已有 GitHub Pages 域名，前端确定后再替换。

## 独立提醒定时函数

新建普通云函数 `threadpilot-reminder-timer`：

- 类型：普通云函数，运行环境 Python 3.11。
- 上传 `dist/threadpilot-reminder-timer.zip`，执行方法 `index.main`。新版同时兼容 `index.main_handler` 和原来的 `timer.main_handler`。
- 超时 120 秒，公网访问开启。
- JSON 环境变量使用本机 `backend/.env.cloudfunction-timer.json`。
- 添加定时触发器，名称 `remindersEveryMinute`，Cron 为 `0 * * * * * *`（每分钟）。
- 创建后先手动测试，返回 `completed` 或 `already_running`。

定时函数经 HTTPS 调用 `/api/internal/reminders/run`，仅持有专用 SCHEDULER_TOKEN。
没有部署定时函数时，已保存的提醒不会自动评估。定时调用会产生函数调用及网络用量。
当前 `BUSINESS_NOW` 固定在演示日期；如需按真实时间提醒，将其改为 `live`。

## 能力边界

- SSE 保留现有 start/delta/done 协议：先完成业务验证，再发送事件，并非逐 token 输出模型推理。
- HTTP 上传的数据写入 MySQL；实例 `/tmp` 文件只是临时副本，不作为永久原始文件存档。
- 本机文件轮询同步在云函数中关闭。需要周期导入时，应另接云存储/上游数据源。
- 催办发送仅在配置 `CHASE_WEBHOOK_URL` 等真实连接器后可用，未配置时保留草稿，不声称已经发送。
- 回复集成使用单独 `REPLY_INGEST_TOKEN`，未配置时拒绝外部回复事件。
- Python 3.11 本地及真实 MySQL/模型联调已验证；Linux ZIP 的最终冷启动、网关超时和 SSE 需要上传后验证。

## 重新构建与测试

从 `backend` 目录执行：

```powershell
uv sync --locked --python 3.11
uv run pytest -q
uv export --locked --no-dev --no-emit-project --no-hashes --format requirements-txt --output-file ../requirements.txt
uv run python -m scripts.cloud_function_config
```

从项目根目录，用安装了 packaging 的 Python 执行：

```powershell
python deploy/cloud-function/export_requirements.py
python -m pip install --target .build/cloud-function-full --platform manylinux2014_x86_64 --implementation cp --python-version 3.11 --only-binary=:all: --no-compile --no-deps -r deploy/cloud-function/requirements-linux311.txt
python deploy/cloud-function/package.py
```

依赖变化后使用干净的 `.build/cloud-function-full` 目录，避免旧版本残留。
ZIP 中 `scf_bootstrap` 已设置 Unix 可执行权限及 LF 换行，不要在 Windows 解压重压。
可选真实联调：在 backend 执行 `python -m scripts.verify_cloud_backend`，会调用模型并仅清理自身测试会话。

参考：[Python HTTP 云函数](https://docs.cloudbase.net/cloud-function/quickstart/httpfunc/python)、
[运行环境与启动路径](https://docs.cloudbase.net/cloud-function/runtime-support)、
[定时触发器](https://docs.cloudbase.net/cloud-function/timer-trigger)。
