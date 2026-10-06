# CloudBase 新加坡部署

目标环境和数据库：`dss5105-track1-i7gxvcy5k7ef5ac9b`。
数据库已完成建表与演示数据导入（120 条订单、360 条生产记录、8 条外协厂），以及完整后端会话表迁移 `0002`。
完整 HTTP 云函数包和配置已准备，下一步按 [HTTP 云函数部署指南](../deploy/cloud-function/README.md) 上传并验证云端运行。

**地域限制更正（2026-10-06）：** CloudBase 官方新加坡地域说明明确暂不提供云托管；当前环境控制台也没有该入口。
因此下文第 3 节的云托管步骤不适用于这个新加坡环境，暂停执行。当前已选择 HTTP 云函数，保留现有 MySQL。
官方说明：https://cloudbase.net/blog/2026/07/27/singapore-region
该公告也描述了 PG 专属环境，与本项目实际已连接的 MySQL 环境不完全一致；不要据此删除现有数据库或迁移数据库类型。

## 1. 本机保存私密配置

在项目的 `backend` 目录打开终端，使用现有 Python 环境：

```powershell
.\.venv\Scripts\python.exe -m scripts.cloudbase configure
```

依次隐藏输入已在云端设置的业务账号密码、AI 账号密码和模型密钥。
数据库密码必须使用控制台当前值；本脚本不会修改云端账号密码。
生成 `backend/.env.cloudbase`，独立于本机 `backend/.env`，已由 Git 和 Docker 忽略规则排除。
不要上传这个文件、把内容粘贴到聊天中或提交到仓库。
CloudBase API Key 不是 MySQL 密码，也不是模型 API Key，本流程不需要它。

脚本使用先前控制台提供的外网地址和端口 26794；如地址变化，更新生成文件中的连接地址。
当前控制台内网显示 `not_support`，不要将该值填入连接字符串。
连接密码中的特殊字符由配置脚本编码。
仅支持 Chat Completions 的模型服务需要将 `INTENT_API_STYLE` 改为 `chat_completions`。

演示时钟默认固定在 `2026-04-01T12:00:00+08:00`，与种子数据时间范围匹配。
正式实时使用应改为 `BUSINESS_NOW=live`。这不会伪造或刷新原始数据日期。

## 2. 建表和导入演示数据

初始化不创建数据库、不创建账号、不重置密码。默认使用用户指定的 `threadpilot_app` 作为迁移账号。
首次初始化需要在目标数据库内具备 CREATE、ALTER、INDEX 以及迁移涉及的 DML 权限；
若迁移涉及删除表或约束，还需对应 DROP 权限。完成后收回运行账号的结构修改权限。
也可通过 `--deploy-user` 指定独立部署账号。权限只授予目标数据库。

```powershell
.\.venv\Scripts\python.exe -m scripts.cloudbase initialize
.\.venv\Scripts\python.exe -m scripts.cloudbase check
```

初始化会再次隐藏询问迁移账号密码，该密码不会另行保存。
流程先执行现有 Alembic 迁移，再用业务账号导入 orders、production_log、workshops 三个项目 CSV。
导入沿用现有业务键/哈希幂等和冲突检测逻辑；不要用此命令覆盖之后的真实业务数据。
三个文件分别提交，不是整体事务；失败后先检查错误原因，已完成部分可能已经落库。
检查命令分别通过业务账号和 AI 账号打印三张表的行数，不调用 AI 或发送外部消息。
查询成功不等于只读权限已验证；AI 账号仅允许三个业务表的 SELECT。
业务账号需要项目库内 SELECT、INSERT、UPDATE、DELETE。

## 3. 云托管参考配置（当前新加坡环境不可用）

- 名称建议：`threadpilot-api`；仅适用于已经确认支持云托管的环境，不能套用于本项目的新加坡环境。
- 构建上下文是 `threadpilot/`，其中包含 Dockerfile、requirements.txt、backend、frontend、data；不是仅上传 backend。
- Git 仓库根目录在上一层，因此从仓库部署时选择 `threadpilot` 子目录。
- Dockerfile：`Dockerfile`；端口：`8000`；启动命令保留镜像默认值。
- 程序读取 `PORT`，绑定 `0.0.0.0`，使用一个 worker。
- 在服务环境变量中逐项配置私密文件中的值；不要把 dotenv 外层引号当成变量值。
- 健康路径 `/api/v1/health` 仅验证进程和模型配置存在，不证明模型可用或数据库可连。
- 公网数据库需要云托管网络可访问外网；绑定 VPC 后仍需验证公网出口与模型接口可达性。
- 已知 VPC `vpc-f85amzv9`、子网 `subnet-p3fafdho`，不能据此推定内网数据库地址可用。

## 4. 上线前尚待处理

目前会话、确认、提醒和通知仍使用 SQLite。容器本地文件是临时的。
正式上线前需要迁移工作流存储到 MySQL，或验证适合 SQLite 锁与事务的持久存储；
不要直接把 SQLite 文件放在对象存储挂载上。单实例并不能解决重启丢失问题。
提醒循环与进程锁当前按单进程设计，后续持久化完成后也先保持单实例，避免多个实例重复评估。
长期提醒要求后台进程持续运行；缩容到零时不会按时检查。

当前 DATA_API_TOKEN 保护管理接口，不是所有聊天接口的访问控制。
开放真实模型调用前需要选择网关鉴权或应用登录方案，避免未授权消耗模型额度。
GitHub Pages 前端不得放入服务端密钥或管理员 token。

## 5. GitHub Pages 接入

取得云托管 HTTPS 服务地址后，编辑 `frontend/config.js` 中的 `apiBase`，只填服务 origin（无 `/api`）。
后端设置 `CORS_ORIGINS=["https://jingweiluo557.github.io"]`。
如网关也配置跨域，确保 OPTIONS 请求可通过且不会重复生成冲突的 CORS 响应头。
前端快照、聊天、通知、证据与数据链接共用该地址。
Pages 发布目录为 `threadpilot/frontend/`，正式发布工作流待服务地址与鉴权方案确定后配置。

参考：
- https://docs.cloudbase.net/run/develop/resource-integration/mysql
- https://docs.cloudbase.net/run/develop/builds/dockerfile
- https://docs.cloudbase.net/run/deploy/configuring/storage/local
