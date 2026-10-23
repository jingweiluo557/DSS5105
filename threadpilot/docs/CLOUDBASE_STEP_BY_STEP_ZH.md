# ThreadPilot：CloudBase 完整部署操作指南

更新：2026-10-16。适用分支：`codex/queue-risk-expedite`。

部署方式：CloudBase SQL 型数据库（MySQL） + 上传 ZIP 的 Python HTTP 后端 + 两个独立定时事件函数 + 连接 Git 的静态前端。不需要启动 Docker。本指南不代表这些云端步骤已经替你执行。

## 1. 先准备好这些东西

| 项目 | 准备内容 |
|---|---|
| Git 仓库 | `https://github.com/jingweiluo557/DSS5105` |
| 分支 | `codex/queue-risk-expedite` |
| 后端主包 | `dist/threadpilot-backend-python311.zip` |
| 提醒任务包 | `dist/threadpilot-reminder-timer.zip` |
| 晨报任务包 | `dist/threadpilot-morning-timer.zip` |
| 数据库 | 同一 CloudBase 环境中的 SQL 型数据库（MySQL），开启直连服务 |
| 模型 | 已配置服务商的有效 API Key、模型和接口地址 |
| 前端地址 F | CloudBase 静态网站最终的 HTTPS 域名 |
| 后端地址 B | 指向 HTTP 云函数根路径的 HTTPS 域名 |

本地 ZIP 在 `D:\GitProjects\DSS5105\threadpilot\dist`。ZIP 和数据库密码不在 Git 分支中；前端代码及构建脚本在分支中。

为避免地址混淆，下文用 B 代表后端，例如 `https://api.example.com`；用 F 代表前端，例如 `https://web.example.com`。这两个示例域名不能直接照填。地址不要带 `/#/ai`、`/api` 等路径。

当前发布包针对 Linux x86_64 / Python 3.11，根目录含 `scf_bootstrap`；启动文件监听 `0.0.0.0:9000`。不要把 ZIP 外面再套一层目录。

## 2. 各部分如何联动

浏览器从 F 下载前端页面，前端再向 B 发送 HTTPS 请求。后端从 MySQL 读取订单和生产数据，用业务服务计算风险和插队影响，必要时请求模型解释或起草，最后将结果返回前端。

晨报定时函数向 B 的 `/api/internal/briefings/run` 发请求；提醒定时函数向 B 的 `/api/internal/reminders/run` 发请求。实际计算与保存由同一个后端完成，所以定时任务和网页使用同一份数据库。

| 连接 | 配置放在哪里 | 内容 |
|---|---|---|
| 前端 → 后端 | 前端构建变量 | `THREADPILOT_PUBLIC_API_BASE=B` |
| 后端允许前端访问 | 后端环境变量 | `CORS_ORIGINS=["F"]` |
| 后端 → MySQL | 后端环境变量 | `DATABASE_URL` 和 `AI_DATABASE_URL` |
| 后端 → 模型 | 后端环境变量 | `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL` |
| 定时任务 → 后端 | 两个定时函数环境变量 | `BACKEND_ORIGIN=B` 和相同的 `SCHEDULER_TOKEN` |
| 用户进入工作台 | 网页连接弹窗 | 输入后端的 `API_ACCESS_TOKEN` |

数据库密码、模型 Key、定时任务 Token 不放在前端。`API_ACCESS_TOKEN` 是现有云端工作台访问凭据；它不是已经移除的“经理审核管理令牌”。经理审核仍通过表单确认执行。

## 3. 第一步：开通 CloudBase SQL 型数据库（MySQL）

### 3.1 在 CloudBase 开通 SQL 数据库与直连服务

本方案使用 CloudBase 自带的 **SQL 型数据库 / MySQL 数据库**。后端保留 SQLAlchemy/PyMySQL 直连方式，现有事务、迁移和只读 SQL 问答服务可以复用；不需要改成浏览器直连或 CloudBase 文档型数据库接口。若控制台提供多个 SQL 引擎，本指南针对 MySQL，不能直接套用于 PostgreSQL。

1. 进入目标 CloudBase 环境，打开「SQL 型数据库」或「MySQL 数据库」。
2. 如尚未初始化，按控制台流程开通，并记录数据库所在地域、VPC 和子网。
3. 进入「数据库设置」→「直连服务」，开启直连。
4. 在「账号管理」创建或确认数据库账号。
5. 记录内网主机、端口、实际数据库名，以及供本地调试使用的外网主机和端口。不要把 CloudBase 环境 ID 当成数据库名。
6. 给后端 HTTP 云函数配置可访问数据库的 VPC/子网，运行时填写数据库内网地址。

官方直连说明支持标准 MySQL 客户端，并列明云函数内网访问需要开启 VPC。外网直连用于本地开发调试，不作为本方案的生产连接方式。[CloudBase 直连服务说明](https://docs.cloudbase.net/database/configuration/db/tdsql/direct-connection)

| 用途 | 使用哪个连接 |
|---|---|
| 云函数运行 | 内网地址、内网端口、运行账户 |
| 本地首次迁移或调试 | 控制台提供的外网地址与端口、对应权限账户 |
| 同 VPC 服务器迁移 | 内网地址、内网端口、迁移账户 |

外网和内网端口不一定相同，必须分别抄录控制台值；不要统一假定都是 3306。完成本地迁移后，可关闭不再需要的外网直连。若暂时没有可用外网入口，在能够访问该数据库的云端机器执行迁移即可。

如果旧环境没有可配置的内网连接，先核对 CloudBase 的实例类型和迁移说明，不要通过猜测内网主机名处理。[旧 MySQL 迁移至自有账号说明](https://docs.cloudbase.net/database/configuration/db/tdsql/migrate-to-user-account)

后端接入 VPC 后，还需确认能够通过 HTTPS 访问模型服务，必要时配置公网出口。数据库连通和模型服务连通是两个独立检查。

### 3.2 建库与三个账户

在 CloudBase 数据库设置中确认实际数据库名；例如控制台可能显示 `tcb`，以你的实例为准，不要求新建一个叫 `threadpilot` 的库。本文用 `DB_NAME` 表示这个实际名称，SQL 中的 `YOUR_DATABASE_NAME` 也要替换为同一名称。建议在专用测试环境完成首次迁移，避免与已有业务表重名。准备三个不同用途的账户：

| 账户 | 用途 | 权限 |
|---|---|---|
| 迁移账户 | 初始化和升级表结构 | 在目标库中执行迁移所需的建表、修改表、索引和数据权限 |
| `threadpilot_app` | 后端运行 | 目标库的 SELECT、INSERT、UPDATE、DELETE |
| `threadpilot_ai` | SQL 问答 | 仅 orders、production_log、workshops 三表的 SELECT |

在 CloudBase「账号管理」或获准的 SQL 管理工具中操作；先确认目标库、迁移表结构，再给 AI 账户授权到具体表。下面是授权示例，前提是账户已建立；账号的主机范围应以你实际创建的账户为准：

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON `YOUR_DATABASE_NAME`.*
TO 'threadpilot_app'@'%';

GRANT SELECT ON `YOUR_DATABASE_NAME`.orders TO 'threadpilot_ai'@'%';
GRANT SELECT ON `YOUR_DATABASE_NAME`.production_log TO 'threadpilot_ai'@'%';
GRANT SELECT ON `YOUR_DATABASE_NAME`.workshops TO 'threadpilot_ai'@'%';
```

不要给 AI 账户写权限，也不要把迁移/管理员账户作为云函数日常运行账户。现有账户若已有更高权限，需先审查并调整；上述 GRANT 不会自动撤销旧权限。不要随意运行 `scripts.provision_mysql` 重置已有共享数据库的账号或授权。

### 3.3 在本地或可访问数据库的服务器执行迁移

使用分支对应的完整源代码；后端上传 ZIP 不包含迁移工具和迁移文件。

下面以本地 Windows PowerShell 为例。如果当前项目已有 `backend/.venv`，可以跳过环境创建和依赖安装。Python 使用 3.11–3.13：

```powershell
Set-Location D:\GitProjects\DSS5105\threadpilot
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location backend

# 使用实际数据库名及迁移入口；本地通常使用外网地址/端口，云内服务器使用内网地址/端口。
$env:DATABASE_URL='mysql+pymysql://MIGRATION_USER:ENCODED_PASSWORD@DB_HOST:DB_PORT/DB_NAME?charset=utf8mb4'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

预期最后显示 `0008_ai_morning (head)`。已有数据库必须先备份；遇到权限错误应使用正确迁移账户，不要跳过迁移直接启动。

密码含 `@`、`:`、`/`、`#`、`%` 等字符时，应对连接 URL 内的密码进行 URL 编码；不要编码整个连接 URL。以上是模板，不要把真实密码提交到 Git 或发送给其他人。

### 3.4 导入数据：新库和已有库分开处理

**已有正式数据：**只升级表结构，不执行种子导入。先核对订单、生产记录和车间数据是否在目标库中。

**新建演示库：**迁移和授权完成后，改用 app 账户连接，再显式导入仓库自带的 CSV：

```powershell
$env:DATABASE_URL='mysql+pymysql://threadpilot_app:ENCODED_PASSWORD@DB_HOST:DB_PORT/DB_NAME?charset=utf8mb4'
.\.venv\Scripts\python.exe -m scripts.init_db --seed-existing --skip-migrate
```

**使用自己的 Excel 文件：**先按数据字典整理，保留备份，在目标正确的前提下运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.init_db --file 'C:\path\source.xlsx' --skip-migrate
```

此命令会写入目标数据库，不能把未经核对的测试表直接导入生产库。字段定义见 `data/dictionary`。

在 SQL 客户端核查：

```sql
SELECT version_num FROM alembic_version;
SELECT COUNT(*) AS orders_count FROM orders;
SELECT COUNT(*) AS production_count FROM production_log;
SELECT COUNT(*) AS workshops_count FROM workshops;
```

完成后关闭含密码的终端，或清理本次设置的环境变量：

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```

## 4. 第二步：上传后端 HTTP 云函数

### 4.1 创建与上传

在 CloudBase 云函数控制台创建或更新一个 **HTTP 云函数**，例如 `threadpilot-api`：

| 设置 | 值 |
|---|---|
| 类型 | HTTP 云函数，不是定时事件函数 |
| 运行时 | Python 3.11 |
| 架构 | 与当前包一致的 x86_64 |
| 上传方式 | 本地 ZIP 上传 |
| 文件 | `threadpilot-backend-python311.zip` |
| 启动 | ZIP 根目录的 `scf_bootstrap` |
| 服务端口 | 9000，代码已设置 |

不需要在云端再次安装 Python 依赖。不要把此包配置为普通的 `index.main` 事件处理函数。HTTP 函数的启动方式与两个定时函数不同。

模型生成可能超过常规短请求时间；在平台允许的范围内，为初始化和请求设置足够的超时，按实际耗时验收。可先以 1 GB 内存作为试运行起点，再根据日志调整；这不是经过压测的容量承诺。

### 4.2 后端环境变量：逐项填写

下表 `DB_HOST`、`DB_PORT` 使用 CloudBase SQL 数据库的内网连接信息；`DB_NAME` 使用实际库名。两个 URL 指向同一个库，但分别使用运行账户和只读账户。

在 CloudBase 环境变量面板填入下表。每个值按原始内容填写，不要照抄 PowerShell 的外层单引号。

| 名称 | 填写值 |
|---|---|
| `DATABASE_URL` | `mysql+pymysql://threadpilot_app:ENCODED_PASSWORD@DB_HOST:DB_PORT/DB_NAME?charset=utf8mb4` |
| `AI_DATABASE_URL` | `mysql+pymysql://threadpilot_ai:ENCODED_PASSWORD@DB_HOST:DB_PORT/DB_NAME?charset=utf8mb4` |
| `OPENAI_API_KEY` | 实际模型密钥 |
| `OPENAI_BASE_URL` | 使用当前服务时为 `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 当前配置使用 `gpt-4.1`；账户需有调用权限 |
| `INTENT_API_STYLE` | `responses` |
| `OPENAI_TIMEOUT_SECONDS` | `60` |
| `API_ACCESS_TOKEN` | 独立生成的工作台访问凭据 |
| `DATA_API_TOKEN` | 另一份独立的数据管理凭据 |
| `SCHEDULER_TOKEN` | 第三份独立的定时任务凭据 |
| `BUSINESS_NOW` | 正式运行用 `live` |
| `CORS_ORIGINS` | `["https://你的前端域名"]` |
| `WORKFLOW_STORAGE` | `database` |
| `BACKGROUND_TASKS_ENABLED` | `false` |
| `MORNING_SCHEDULER_ENABLED` | `false` |
| `SYNC_ENABLED` | `false` |
| `SERVE_FRONTEND` | `false` |

三个 Token 必须不同，启动脚本会校验。可以在自己的电脑上用 `python -c "import secrets; print(secrets.token_hex(32))"` 分别生成，并保存到你自己的安全位置。

启动脚本会强制使用数据库保存工作流、关闭进程内后台任务、文件同步和前端托管。上表仍列出来，便于对照。云函数不能依靠本地 SQLite 持久保存会话，也不会自动导入 CSV。

`CORS_ORIGINS` 是 JSON 数组，内部双引号必须保留。可同时允许正式域名和测试域名，例如 `["https://web.example.com","https://preview.example.com"]`。不要填 `/#/ai` 或页面路径。

如果需要复现当前历史数据的验收结果，可暂时设置 `BUSINESS_NOW=2026-04-01T09:00:00+08:00`。正式实时运行应使用 `live`。业务时间改变会改变逾期数量，这是预期行为；固定业务时间不会改变定时器的真实触发时间。

催办外发是可选集成：只有配置 `CHASE_WEBHOOK_URL`、`CHASE_WEBHOOK_TOKEN` 并验证真实网关回执后，才能称为实际发送。`REPLY_INGEST_TOKEN` 用于上游回复事件。没有这些配置时，不应把草稿或站内记录当成已送达消息。

### 4.3 配置 HTTP 访问地址 B

为该 HTTP 函数配置 HTTPS 访问入口，并确保域名的 `/api/...` 请求被转发给这个函数。前端构建脚本只接受后端“域名根地址”，不支持带 `/function-name` 的路径前缀。

如果平台默认地址带函数名路径，需要配置域名根路径映射，或使用能直接映射到该函数的独立域名。API 请求不能误转到前端静态页面。

先访问 `B/api/v1/health`。预期返回类似：

```json
{"status":"ok","configured":true,"model":"gpt-4.1","streaming":true}
```

这个结果只证明服务响应和模型客户端已配置，不证明模型余额、数据库内容或 SSE 网关行为全部正常。后端根路径 `/` 返回 404 并不一定是故障，因为后端没有托管前端。

再用工作台 Token 验证数据接口。PowerShell 示例：

```powershell
$backendOrigin='https://你的后端域名'
$workspaceToken=Read-Host 'Workspace access token'
Invoke-RestMethod "$backendOrigin/api/snapshot" -Headers @{'X-ThreadPilot-Token'=$workspaceToken}
```

应该返回 orders 等数据。不要把包含业务数据的完整结果公开粘贴；不带 Token 请求此接口应返回 401。

## 5. 第三步：部署两个定时事件函数

### 5.1 提醒函数

新建 **事件函数**，例如 `threadpilot-reminder`：

| 设置 | 值 |
|---|---|
| 运行时 | Python 3.11 |
| ZIP | `threadpilot-reminder-timer.zip` |
| 执行入口 | `index.main_handler`，也提供 `index.main` 别名 |
| `BACKEND_ORIGIN` | B，后端 HTTPS 根地址 |
| `SCHEDULER_TOKEN` | 与后端完全相同 |

该函数使用标准库，不需要额外数据库账户或模型密钥。它通过 HTTPS 调用后端；网络必须能访问 B。

创建定时触发器，例如每分钟一次。若控制台使用腾讯 SCF 七字段 Cron，示例为：

```text
0 */1 * * * * *
```

手动测试时传 `{}` 即可。正常返回 `completed` 或 `already_running`。无到期提醒时 `completed` 也正常，并不表示一定生成了通知。

实际验收：在网页创建并确认一个未来到期的提醒，等待满足时间和条件，再检查站内通知。当前提醒是站内通知，不是自动发送手机短信。

### 5.2 晨报函数

另建 **事件函数**，例如 `threadpilot-morning`：

| 设置 | 值 |
|---|---|
| 运行时 | Python 3.11 |
| ZIP | `threadpilot-morning-timer.zip` |
| 执行入口 | `index.main_handler`，也提供 `index.main` 别名 |
| `BACKEND_ORIGIN` | 同一个 B |
| `SCHEDULER_TOKEN` | 与后端完全相同 |

配置每天北京时间 07:00 触发。若触发器按北京时间解释七字段 Cron：

```text
0 0 7 * * * *
```

若界面明确按 UTC 解释，则北京时间 07:00 对应 UTC 前一天 23:00，使用：

```text
0 0 23 * * * *
```

**必须查看控制台显示的下一次触发时间确认时区。不要仅凭函数日志时间或 `TZ` 环境变量推断触发器时区。** 若控制台接受不同字段数量，按该界面的调度形式填写，不要强行粘贴七字段表达式。

晨报在北京时间 07:00 前通过“定时接口”手动测试会得到尚未到时间的结果，当前定时包装代码会把它记为失败。请在 07:00 后测试该事件函数；需要随时测试生成时，用网页的 Generate briefing 或普通生成接口。

两个定时函数内部 HTTP 等待上限目前均为 90 秒，事件函数超时应留出网络开销并与平台允许值匹配；后端和网关也需允许完整请求。晨报有生成与核验两个模型步骤，可能耗时较长。超时后先查看后端日志和已保存报告，不能单凭定时函数超时判断没有生成。

正常晨报返回 `completed`、`already_saved` 或 `already_running`。同日定时生成会检查已有报告，重复触发不应理解为每次重新生成。关闭网页后，云端触发器仍可调用后端。

## 6. 第四步：CloudBase 前端连接 Git 分支

### 6.1 创建静态网站/应用部署

在 CloudBase 静态网站的 Git 部署入口连接 GitHub 仓库，选择分支 `codex/queue-risk-expedite`。根据控制台字段配置：

| 设置 | 值 |
|---|---|
| 仓库 | `jingweiluo557/DSS5105` |
| 分支 | `codex/queue-risk-expedite` |
| 项目/根目录 | `threadpilot` |
| 框架 | 静态项目 / 自定义 |
| 安装命令 | 留空；没有 npm 依赖。如必须填写，可用 `node --version` |
| 构建命令 | `node deploy/build_frontend.cjs` |
| 输出目录 | `dist/frontend` |
| 发布路径 | `/` |
| 构建环境变量 | `THREADPILOT_PUBLIC_API_BASE=B` |

构建环境要有 Node.js。脚本只使用 Node 内置模块，不需要安装前端依赖。

如果平台从仓库根目录执行命令且无法设置项目目录，则改用：

- 构建命令：`node threadpilot/deploy/build_frontend.cjs`
- 输出目录：`threadpilot/dist/frontend`

不要同时使用两套路径。不要把 `backend` 作为前端输出目录，也不要发布整个仓库。

### 6.2 配置前后端互信

1. 在前端构建变量中填写真实 B，并运行构建部署。
2. 获取前端实际 HTTPS 地址 F。
3. 将后端 `CORS_ORIGINS` 更新为 `["F"]`，保存并重新部署/重启后端实例使其生效。
4. 打开 F，出现 “Connect to your workspace” 时输入 `API_ACCESS_TOKEN`。
5. 查看 Dashboard、AI workspace、Risk orders 和 `F/briefing.html`。

前端构建变量只在构建时注入：修改后端地址后，必须重新构建前端。不要只修改变量却继续使用旧静态产物。

应用 Token 保存在当前浏览器标签页的 sessionStorage；换浏览器或新会话可能需要重新连接。定时函数使用的是 `SCHEDULER_TOKEN`，不是工作台 Token。

### 6.3 页面更新与缓存

静态站点独立于 Python 后端，后端的缓存响应头不能控制 CloudBase 静态 CDN。部署后若仍看到旧按钮或旧布局，检查构建日志、分支、产物目录，并更新/刷新 HTML 和 config.js 的缓存。页面和 API 同时更新时，应先验证后端兼容，再发布前端。

首次直接访问 `F/briefing.html` 也应工作；应用其他页面使用 `/#/ai` 等 hash 路由。

## 7. 第五步：逐项验收联动

| 检查 | 操作 | 通过标准 |
|---|---|---|
| 后端启动 | 打开 B/api/v1/health | JSON 返回 ok，不是 HTML |
| 数据库内容 | 带工作台 Token 请求 /api/snapshot | 订单、生产记录来自目标 MySQL |
| 访问控制 | 不带 Token 请求 /api/snapshot | 返回 401 |
| 前端连接 | 打开 F，连接工作台 | 页面加载正确数据，不请求 localhost |
| 多轮问答 | 查一个存在的订单，再问它的风险 | 保留订单上下文，英文回答，证据与记录一致 |
| 流式输出 | AI workspace 发起需要模型解释的问题 | 完成前已出现部分正文，随后继续增加 |
| 风险与插队 | 对同订单查看风险、分析插队 | 展示自身收益、受影响订单和同一份数据依据 |
| 草稿恢复 | 起草理由、手动修改、刷新 | 编辑内容恢复，没有静默覆盖 |
| 审核确认 | 使用测试订单检查预览和最终确认 | 未确认不调整排程；重复确认不重复产生效果 |
| 晨报手动生成 | 点击 Generate briefing | 保存真实模型报告，重点和待办英文分点 |
| 晨报定时生成 | 北京时间 07:00 后测试事件函数 | 正常状态，网页能看到保存的报告 |
| 提醒定时 | 创建已确认、将到期的测试提醒 | 到期且条件满足后有站内通知，不重复产生 |
| 持久化 | 重启云函数后重新打开草稿/会话 | 数据仍可从数据库恢复 |
| 手机访问 | 用手机访问 F | 请求 B，页面与电脑使用同一数据库 |

SSE 必须通过真实 B 和实际前端验收。浏览器开发者工具中查看 `/api/v1/workflow/chat/stream`，应收到 `start`、多次 `delta`、最后 `done`。如果一直等到结尾才出现全部文本，检查 CloudBase 访问链路是否缓冲 SSE，以及网关超时限制；本地测试通过不能证明公网流式一定有效。`error` 事件表示失败，即使 HTTP 状态为 200。

后端已发送 `X-Accel-Buffering: no`，但中间网关是否尊重该头需实测。若所选 HTTP 访问方式不支持逐段传输，需要采用支持流式的入口；不能通过前端“打字动画”替代真实 SSE。

## 8. 常见问题对照

| 现象 | 优先检查 |
|---|---|
| 云函数启动失败 | HTTP 类型、Python 3.11、ZIP 根目录 bootstrap、必填环境变量、三个 Token 是否不同 |
| scf_bootstrap 找不到 | 是否二次压缩多套了一层文件夹；是否误用其他包 |
| 数据库连接超时 | DB_HOST 是否云内网地址、后端网络/VPC、端口和访问规则 |
| Access denied | 账号密码、URL 编码、来源主机授权 |
| Table does not exist | 是否在正确数据库迁移到 0008_ai_morning |
| 健康检查正常但 AI 失败 | 模型账户权限/额度、模型名称、接口协议、公网出口 |
| 页面显示 Failed to fetch | B、HTTPS、F 是否在 CORS 列表、后端是否实际可达 |
| 反复出现连接弹窗 | 输入的是否 API_ACCESS_TOKEN，而非 DATA_API_TOKEN 或 SCHEDULER_TOKEN |
| API 返回 HTML / JSON 解析失败 | API 域名是否误指向静态网站，路径映射是否正确 |
| 定时函数 401 | SCHEDULER_TOKEN 是否与后端一致；是否被网关额外鉴权拦截 |
| 晨报定时函数测试失败 | 是否在北京时间 07:00 前，模型是否可用，是否超过 90 秒 |
| 手机无法访问 | 是否误用了 localhost/127.0.0.1；检查前端构建变量 |
| 逾期数量与演示不同 | BUSINESS_NOW 是 live 还是固定演示时间；数据是否同一份 |
| 会话重启后丢失 | 是否真的由 cloud_serve 启动，WORKFLOW_STORAGE 是否 database |
| 改了变量但没效果 | 后端变量需要生效到新实例；前端变量需要重新构建 |
| 催办没有真正发出 | 网关未配置、回执未知或没有完成确认；草稿不代表已发送 |

## 9. 后续更新顺序

1. 备份数据库，并记录当前后端 ZIP、前端提交号和配置。
2. 查看新版本是否有数据库迁移，有则先执行并验证。
3. 上传新后端 ZIP，检查健康、数据和关键接口。
4. 按需要更新定时函数 ZIP，保持 Token 和后端地址一致。
5. 发布对应 Git 前端版本，确认构建变量和缓存。
6. 重做主要联动检查。回退代码前确认数据库兼容；不要盲目降级已有新数据的数据库。

当前这些 ZIP 的完整性和依赖版本已检查，上一轮后端测试为 120 通过、1 跳过。实际 CloudBase 网络、MySQL 授权、迁移、触发器和公网 SSE 仍需按本指南验收。

## 10. 官方资料与项目文档

以下官方资料用于核对平台操作；具体控制台名称可能调整，以当前页面为准：

- [CloudBase SQL/MySQL 直连服务](https://docs.cloudbase.net/database/configuration/db/tdsql/direct-connection)
- [CloudBase Python HTTP 函数部署](https://docs.cloudbase.net/cloud-function/quickstart/httpfunc/python)
- [CloudBase 运行时与 Python 绝对路径](https://docs.cloudbase.net/cloud-function/runtime-support)
- [HTTP 启动文件 scf_bootstrap](https://docs.cloudbase.net/cloud-function/develop/scf-bootstrap)
- [CloudBase Git / 静态网站部署](https://docs.cloudbase.net/hosting/web-hosting)
- [构建命令、产物目录和环境变量](https://docs.cloudbase.net/cli-v1/hosting)
- [腾讯云定时触发器与七字段 Cron](https://cloud.tencent.com/document/product/583/9708)

项目文档：[英文部署说明](CLOUD_DEPLOYMENT.md)、[英文工具说明](TOOL_SPECIFICATION_SPRINT1.md)、[流式接口](../backend/STREAMING_API.md)、[验证记录](RELEASE_VALIDATION.md)。
