# 从 GitHub 发布当前已联调版本

2026-10-06 验证：后端 83 项测试通过、1 项跳过；两组模拟浏览器测试通过；真实 CloudBase 浏览器联调通过。
真实联调覆盖访问令牌拒绝/登录、云端 120 条订单、两轮模型问答、SSE、证据、刷新恢复、通知查询、退出和手机布局。
测试不确认业务写入，不发送催办；这不代表全部业务场景和生产负载已验证。

## 1. 前端 Git 部署

进入 CloudBase 环境 `dss5105-track1-i7gxvcy5k7ef5ac9b` → 静态网站托管 → Git 个人仓库部署。

| 字段 | 值 |
|---|---|
| Git 仓库 | `jingweiluo557/DSS5105` |
| 分支 | `codex/ai-workspace-demo` |
| 应用名称 | `threadpilot-web` |
| 框架 | 其他 / 纯静态 |
| 目标目录（工作目录） | `threadpilot/frontend` |
| 安装命令 | 留空 |
| 构建命令 | 留空 |
| 构建产物目录 | `.`，相对上述工作目录 |
| 部署路径 | `/` |
| 构建环境变量 | 不需要密钥 |

如果页面没有工作目录字段，保留仓库根目录，构建产物目录填 `threadpilot/frontend`。
不要把仓库根目录作为公开网站产物；后端代码与私密配置不属于前端。
后续更新需推送到同一分支，并在控制台重新部署或配置自动部署。

## 2. 网关与跨域

前端 config.js 已设置公开环境的后端地址：
`https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com`
API 地址不附加 `/api`，前端请求本身已含该前缀。

保留 `/api` 路由指向完整 HTTP 后端，开启路径透传。
如果前端和后端使用同一个域名，`/` 应指向静态托管，而不是旧探针；最长前缀匹配会把 `/api/...` 留给后端。
如果使用独立静态托管域名，将实际前端 origin 同时加入：

1. 后端函数环境变量 `CORS_ORIGINS`（JSON 数组字符串）。
2. HTTP 网关跨域允许域名。

保留已有本地联调 origin 时，例如：
`["http://127.0.0.1:8765","https://你的实际前端域名"]`
不要填 URL 路径。允许的请求头包括 `Content-Type`、`X-ThreadPilot-Token`、`Authorization`、`X-Confirm-Write`。

## 3. 首次使用

打开前端后，输入本机 `backend/.env.cloudfunction.json` 的 `API_ACCESS_TOKEN` 字段值。
只填写这个应用访问令牌；不能使用模型密钥、数据库密码、DATA_API_TOKEN 或 SCHEDULER_TOKEN。
令牌仅保存在当前浏览器标签页的 sessionStorage，不写入 Git 或公开配置。
它是团队共享访问方式，不是独立用户账号体系。Settings → Disconnect workspace 可清除访问和本地会话。
证据链接现在会在页面内读取并展示，避免地址栏请求缺少鉴权。

## 4. 后端如何更新

静态托管的 Git 部署只部署前端，不会更新 HTTP 云函数。
本次真实测试已调用线上完整后端，前端鉴权修复不要求重新上传主函数。
未来后端代码变更后，从对应 Git 提交按 `deploy/cloud-function/README.md` 构建 Linux Python 3.11 包，再上传云函数。
也可后续配置 CI/CD 来构建和部署，但当前尚未配置腾讯云部署凭证和自动云函数发布流水线。
提醒函数需单独部署和启用 timer；本次浏览器测试验证通知接口，不证明定时触发器已启用。

## 5. 发布后验收

打开网站 → 输入访问令牌 → 看到 120 条订单 → 查询 ORD-005 → 打开证据 → 刷新后追问 → Settings 退出。
检查浏览器没有 CORS/401/404 错误；登录前 401 是正常的访问控制结果。
开发默认域名适合联调，长期公开发布须核对 CloudBase 默认域名限制并配置正式域名。

参考：[静态托管构建配置](https://docs.cloudbase.net/hosting/web-hosting-guide)、[网关路由匹配](https://docs.cloudbase.net/service/routes)。
