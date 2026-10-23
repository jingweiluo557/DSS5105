# 当前 CloudBase 部署核查与下一步操作

> **2026-10-23 执行更新：第一步数据库迁移已完成。** 按用户明确要求跳过备份；切换本地网络后数据库直连恢复。目标库 `dss5105-track1-i7gxvcy5k7ef5ac9b` 已通过项目原有 Alembic 迁移从 `0005` 升级至 `0008_ai_morning`，新增 `dispatch_schedule`、`dispatch_reviews`、`dispatch_drafts`、`ai_morning_reports`，并确认草稿订单索引存在。迁移前后逐表核对行数与内容 SHA-256，18 张原有业务表全部一致；订单 120 条、生产记录 360 条、车间配置 8 条。未重新导入数据，未调整账号权限。核验记录保存在本地 `.build/cloudbase-migration-20261023/verification.json`（仅统计与校验值，不是数据库备份）。以下旧配置记录保留供后续步骤参考，其中“当前版本 0005”和“待迁移”描述已由本更新取代；后端、前端及定时任务尚待分别验收。

整理日期：2026-10-17。配置依据为上一轮已登录控制台的只读检查（页面中最新部署记录为 2026-10-16）。本轮继续检查时登录已过期，因此没有补查运行日志。以下是已观察到的配置，不代表之后的云端状态不会改变。本次没有修改任何云端配置或数据库。

## 1. 结论

不需要重新创建整个环境。优先完成：**备份与数据库迁移 → 后端接口检查 → 前端地址注入与 CORS → 更新现有提醒函数 → 新建晨报函数 → 联动验收**。

“上传成功/Normal”只表示平台部署状态，不等于应用接口已经正常工作。实际打开前端时，页面显示：`Unable to load current data: Database unavailable. Check migrations and connection settings.`。数据库确实缺少本版本要求的表，但在未读取错误日志前，不能断言这就是该提示的唯一原因。

## 2. 已确认的现状

| 项目 | 控制台实际值 | 判断 |
|---|---|---|
| 环境 | dss5105-track1-i7gxvcy5k7ef5ac9b；新加坡 | 保留 |
| SQL 引擎 | MySQL 8.0；Self-owned instance | 已有数据库，无须重建 |
| 实际库名 | dss5105-track1-i7gxvcy5k7ef5ac9b | 本环境的库名恰好与环境 ID 相同；不要改成 threadpilot 或 tcb |
| 当前迁移版本 | alembic_version = `0005` | 升级到 `0008_ai_morning` |
| 现有数据表 | orders、production_log、workshops、workflow_*、dashboard_* 等 | 保留，未核查各表当前行数 |
| 数据库账户 | threadpilot_app、threadpilot_ai、内置 root | 账户存在；没有查看密码，具体授权尚未核查 |
| 公网直连 | 已开启；端口 26794 | 与通用示例 3306 不同 |
| 内网地址 | `not_support` | 不能当作有效主机名使用 |
| 数据库 VPC | vpc-f85amzv9 / subnet-p3fafdho | 有网络信息，不等于当前云函数已能内网连接 |
| 数据库自动暂停 | 开启，空闲 30 分钟后暂停 | 冷启动可能影响首请求；备份前确认手动备份完成 |
| 后端 threadpilot-api | Normal；Python 3.11；端口 9000；1024 MB；300 秒 | 配置类型正确，更新于 2026-10-16 20:27:33 |
| 后端网络 | 公网访问开；VPC 未开启 | 未确认被遮蔽连接 URL 的实际主机，不能直接断定数据库走哪条链路 |
| WORKFLOW_STORAGE | database | 正确，保留 |
| BUSINESS_NOW | 2026-04-01T12:00:00+08:00 | 演示时间，复现历史数据时保留；正式实时运行再改 live |
| CORS_ORIGINS | 仅 https://jingweiluo557.github.io | 缺少当前 CloudBase 前端域名 |
| 前端 | threadpilot-003，Successful，2026-10-16 20:12:25 | 静态文件已部署 |
| 前端发布配置 | 目录 threadpilot/frontend；无构建命令；无环境变量；部署命令 tcb hosting deploy . / | 没有运行后端地址注入脚本，应按第 5 节更新 |
| 正常提醒函数 | threadpilot-reminder-timer-v2 | 已存在，可更新，无须再建重复提醒函数 |
| 旧失败提醒函数 | threadpilot-reminder-timer | 创建失败记录；本次没有删除 |
| 晨报定时函数 | 四项函数清单中没有晨报函数 | 需要新建 |

账号存在不等于权限正确；变量名存在不等于变量值正确。本次仅展开业务时间、CORS、存储模式和提醒的后端地址等非秘密配置，没有展开数据库密码、模型 Key 或 Token。

## 3. 第一步：备份并升级现有数据库

### 3.1 先备份与确认目标

在当前 CloudBase SQL 数据库的数据库设置页点击手动备份，并确认备份成功。备份是你下一步要执行的操作，本次没有创建。

在 SQL editor 选择库 `dss5105-track1-i7gxvcy5k7ef5ac9b`，先执行只读检查：

```sql
SELECT DATABASE();
SELECT version_num FROM alembic_version;
SHOW TABLES;
```

若仍显示 `0005`，按下面迁移。若已变更版本，先以实际结果为准，不要手工改写版本号。

### 3.2 本次只需三个迁移

| 迁移 | 新增表 | 功能 |
|---|---|---|
| 0006_dispatch | dispatch_schedule、dispatch_reviews | 排程优先级、插队分析与经理决策 |
| 0007_drafts | dispatch_drafts | 审核理由草稿、版本和恢复 |
| 0008_ai_morning | ai_morning_reports | 真实模型晨报归档 |

这些升级不会要求删除或重新导入现有 orders/production_log/workshops。不要运行种子导入，也不要仅将 alembic_version 改成最新编号，否则表结构仍然缺失。

### 3.3 使用具备迁移权限的账号执行

现有 `threadpilot_app` 和 `threadpilot_ai` 的具体授权未核查；不要假设它们拥有 CREATE/ALTER 权限。使用有目标库迁移权限的专用账号；若没有，先在控制台准备合适的迁移账号。

在本地 PowerShell 使用已有项目环境执行（替换 USER 和编码后的密码）：

```powershell
Set-Location D:\GitProjects\DSS5105\threadpilot\backend
$env:DATABASE_URL='mysql+pymysql://MIGRATION_USER:ENCODED_PASSWORD@sg-cynosdbmysql-grp-fe15p52v.sql.tencentcdb.com:26794/dss5105-track1-i7gxvcy5k7ef5ac9b?charset=utf8mb4'
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```

这是控制台已显示的公网调试入口；执行前确认它仍开启且你的网络被允许。密码不要发到聊天或写入 Git。若权限错误，停止并调整迁移账户，不要强行跳过。MySQL 表结构变更不能简单依靠事务完全回滚，失败后先检查已完成步骤。

预期最终为 `0008_ai_morning (head)`。再次执行 `SHOW TABLES` 确认四张新表存在。然后确认运行账户能读取/写入新表；AI 账户仍只需读取三张业务表。

控制台关于 `_openid` 的提示针对 CloudBase SDK 权限体系；本后端使用 MySQL 直连，不要为了消除提示擅自给所有迁移表添加字段。

## 4. 第二步：保持现有网关，先验证后端

已确认公共后端根地址 B：

```text
https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com
```

当前网关路由：

- `/api` → `threadpilot-api`，启用，**路径透传开启**。
- `/` → `threadpilot-api-test`，旧测试函数，路径透传未开启。

前端和定时器使用 `/api/...` 接口，所以可以先保留 `/api` 路由完成验收。**前端配置 B 时不要再加 `/api`**，否则代码会拼成 `/api/api/...`。不要通过访问根页面或 `/docs` 来判断正式 API，因为根路由目前仍指向测试函数。后续如要统一根路由，应单独评估测试入口的使用情况。

迁移后先访问：

```text
B/api/v1/health
```

再通过工作台连接或带 `X-ThreadPilot-Token` 的只读请求测试 `/api/snapshot`、`/api/scheduling/risk` 和 `/api/morning`。不要把 token 写进 URL。健康检查成功不能证明所有数据库接口成功。

如果仍然数据库不可用，打开 `threadpilot-api` 的日志，按错误类型检查：

- Table does not exist：迁移到了别的库或迁移不完整。
- Access denied / command denied：账号密码或权限。
- Connect timeout：数据库自动暂停、网络或连接地址。

数据库设置页显示内网 `not_support`，后端 VPC 未启用。不要把 DATABASE_URL 主机改成 `not_support`。生产内网接入需要根据当前实例的可用能力另行配置和验证，本次未验证。现有公网调试路径可用于迁移排错，但不能将其直接描述为已经完成内网生产接入。

## 5. 第三步：修正前端构建和后端 CORS

2026-10-23 实测：正式后端 `/api/v1/health`、`/api/snapshot`、`/api/scheduling/risk`、`/api/morning` 均返回 200，CloudBase 前端来源的预检与实际响应均允许跨域。线上前端 `config.js` 的 `apiBase` 仍为空，导致请求静态站点的 `/api/snapshot` 并收到 404，界面将其统一显示为数据库不可用。前端发布 `threadpilot-004` 因平台不允许直接以 `node` 开头的构建命令而失败。随后 npm exec 入口在 CloudBase 报 EUSAGE；现已在项目根目录增加 package.json，使用标准 npm run build 入口，仍需重新发布验收。控制台浏览器自动审批受限，最后的发布操作暂需用户手动执行。

### 5.1 更新现有前端 threadpilot，避免新建重复站点

当前发布配置直接上传 `threadpilot/frontend`，没有使用已提供的构建脚本。建议更新为：

| 字段 | 填写值 |
|---|---|
| Git 分支 | codex/queue-risk-expedite（需在更新页确认，之前只读详情未显示分支名） |
| Target Directory | threadpilot |
| Installation Command | 留空；如必填可用 node --version |
| Build Command | npm run build |
| Build Artifact Directory | dist/frontend |
| Deployment Path | / |
| 环境变量名 | THREADPILOT_PUBLIC_API_BASE |
| 环境变量值 | 上面完整的 B，末尾不要加 /api |

2026-10-23 控制台提供“目标目录、构建命令、产物目录、部署路径”字段。使用上表从生成目录发布，不再直接上传源目录。构建日志应出现 `Static frontend prepared in dist/frontend. Backend: ...`。npm run build 通过 package.json 调用已有构建脚本，不需要安装依赖；请确保 Git 分支包含新增的 threadpilot/package.json。

发布成功后，重新检查线上 `config.js` 已写入 B，并在浏览器验收 Dashboard；平台显示 Successful 不能代替实际页面验收。

### 5.2 更新正式后端 CORS_ORIGINS

已确认应用详情中的前端地址 F：

```text
https://threadpilot-dss5105-track1-i7gxvcy5k7ef5ac9b.webapps.tcloudbase.com
```

在 `threadpilot-api` 的环境变量中，将 CORS_ORIGINS 更新为：

```json
["https://threadpilot-dss5105-track1-i7gxvcy5k7ef5ac9b.webapps.tcloudbase.com","https://jingweiluo557.github.io"]
```

这里保留旧 GitHub Pages 来源，避免影响旧入口。若你只使用 CloudBase 前端，可经确认后删除不再使用的旧来源。

部署日志还提供了静态托管默认域名 `https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.intl.tcloudbaseapp.com`。如你也使用该域名，应把它作为另一个准确来源加入数组；不要添加路径。保存环境变量后让配置生效到新实例。

网关已显示 CORS Enabled，但其详细允许来源和请求头本次没有检查。若应用层更新后仍跨域失败，再核对网关是否允许你的前端来源、OPTIONS、Content-Type 和 X-ThreadPilot-Token；不要仅因为显示 Enabled 就认为所有跨域条件都满足。

## 6. 第四步：更新现有提醒函数

使用 **threadpilot-reminder-timer-v2**，不用新建第三个提醒函数。

已确认：Python 3.11、1024 MB、120 秒、入口 `index.main`；触发器 `remindersEveryMinute`，表达式 `0 * * * * * *`。已配置 BACKEND_ORIGIN 为 B，也已存在 SCHEDULER_TOKEN。

操作：

1. 上传 `dist/threadpilot-reminder-timer.zip` 更新 v2 的代码。
2. 保留 `index.main`，新包支持此别名。
3. 保留现有每分钟触发器，避免重复添加。
4. 确认 SCHEDULER_TOKEN 与正式后端一致（本次未揭示或比较秘密值）。
5. 数据库和后端接口正常后手动测试 `{}`，预期 completed 或 already_running。

创建失败的 `threadpilot-reminder-timer` 先不用管；它与正常的 v2 是两个对象，本次没有删除任何函数。已有提醒触发器可能已经周期运行，不能说提醒功能完全没有部署。

## 7. 第五步：新建晨报事件函数

当前函数清单没有晨报任务。新建 `threadpilot-morning-timer`：

| 字段 | 值 |
|---|---|
| 类型 | 普通事件云函数，非 HTTP |
| 运行时 | Python 3.11 |
| ZIP | dist/threadpilot-morning-timer.zip |
| 入口 | index.main 或 index.main_handler |
| 超时 | 120 秒作为初始设置；包内 HTTP 等待上限 90 秒，需按实测检查 |
| BACKEND_ORIGIN | B |
| SCHEDULER_TOKEN | 与 threadpilot-api 相同 |

在数据库升级和网页手动生成晨报成功后，再配置每天北京时间 07:00 的触发器。按北京时间解释的七字段表达式为 `0 0 7 * * * *`；若控制台明确按 UTC，则对应 `0 0 23 * * * *`。以“下一次触发时间”为准，不要仅修改函数 TZ 就认为改变了触发器时区。

定时接口在北京时间 07:00 前不会生成，当时手动测试包装函数可能报未到时间；普通网页 Generate briefing 不受该定时门槛限制。模型生成需要真实可用的服务，失败不能用模拟晨报代替。

## 8. 最后验收顺序

1. 数据库版本为 0008_ai_morning，四张新表存在，原订单数据保留。
2. 正式 `/api` 健康和数据接口正常。
3. 重新部署前端，打开 F，输入 API_ACCESS_TOKEN 后正常显示 Dashboard。
4. 风险、插队分析、理由草稿及刷新恢复正常。
5. 人工生成一次晨报，确认英文分点和数据库归档。
6. 提醒与晨报事件函数手动测试成功，再观察计划触发日志。
7. 测试真实 SSE 增量输出、手机访问和云函数重启后的持久化。

本次观察不能证明：云端模型调用已成功、迁移账号具备 DDL 权限、密钥值互相匹配、线上 API 均可用或真实 SSE 已通过。后台 Normal 和前端 Successful 不能替代这些验收。

通用操作细节见 [完整部署指南](CLOUDBASE_STEP_BY_STEP_ZH.md)。本文件优先描述你当前环境的差异，不要求重建环境或重新导入订单。
