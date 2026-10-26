# 本次 CloudBase 更新指南（2026-10-12，合并 footoonming 的 PR 之后）

在 [CLOUDBASE_UPDATE_20261010.md](CLOUDBASE_UPDATE_20261010.md) 的基础上只多三件事：后端重新打包、数据库跑一次迁移 0006、前端改用 `main` 分支。
其余配置（数据库、AI Key、令牌、定时函数、跨域）保持不变。

## 0. 合并

GitHub 上合并 PR（`footoonming:merge-footoonming-briefing` → `main`）。该分支已包含 `codex/dashboard-forecast-email` 的全部提交，
与 `main` 合并无冲突，合并后全部测试通过（根目录 198 项、backend 135 项）。

## 1. 后端（先做）

```
cd threadpilot
python -m pip install --target .build/cloud-function-full --platform manylinux2014_x86_64 --implementation cp --python-version 3.11 --only-binary=:all: --no-compile --no-deps -r deploy/cloud-function/requirements-linux311.txt
python deploy/cloud-function/package.py
```

上传 `dist/threadpilot-backend-python311.zip` 到 `/api` 关联的 HTTP 云函数并部署（同 10-10 指南第 1 节）。新 ZIP 已包含
`simulation/` 里的发现与风险引擎，无需另外上传。

可选的新环境变量（不填即用默认值）：

| 变量 | 默认 | 作用 |
|---|---|---|
| `CHAT_REQUESTS_PER_MINUTE` | 40 | 每个访问者每分钟最多调用模型的次数，超过返回 429；0 为关闭。公开链接防止刷 OpenAI 费用 |
| `OPENAI_MAX_RETRIES` | 2 | OpenAI 限流或断线时的重试次数上限 |
| `BRIEFING_EMAIL_TO` | 空 | 日报邮件第一次的默认收件人，逗号分隔；之后自动沿用上一次的收件人 |

## 2. 数据库迁移 0006（一次）

在本机 `threadpilot/backend` 目录运行（会提示输入迁移账号密码，不保存）：

```
python -m scripts.cloudbase initialize
python -m scripts.cloudbase check
```

新增一张表 `briefing_email_deliveries`（收件人与发送记录），不改动已有表；演示数据重复导入不会产生副本。
**没跑之前网站也能用**：邮件草稿照常生成、编辑、保存，只是不记住收件人、不记录"已发送"。

## 3. 前端

CloudBase → 静态网站托管 → Git 配置：分支从 `codex/dashboard-forecast-email` 改为 **`main`**，其他字段不变，重新部署。
（`config.js` 和 `index.html` 已更新缓存版本号，用户刷新即可拿到新版本。）

## 4. Outlook 发送（不需要任何配置）

邮件对话框的 **Open in Outlook** 会在新窗口打开 Outlook 网页版"新邮件"，收件人、主题、正文已填好，总经理在 Outlook 里点发送。
`config.js` 中 `outlook.web`：工作/学校 Microsoft 365 账号用 `'office'`（默认），Outlook.com / Hotmail 用 `'live'`。
一键直发（**Send with Outlook**）需要先在 Microsoft Entra 注册应用，见 [outlook_setup.md](outlook_setup.md)；不做也不影响。

## 5. 验收

- `/api/v1/health` 正常；手机打开网站，各页面不能左右滑动。
- Dashboard → Generate email：出现 To / Cc 栏；填自己的邮箱 → Open in Outlook → Outlook 新窗口内容正确。
- 左侧菜单 **Morning Briefing** 可打开；AI 里问 "What's wrong today?" 返回今天的发现（风险等级与日报一致）。
- 迁移后：发送一次后重新打开邮件，To 栏保留。

## 6.（顺便）真实模型评测，一次

这一步在本机 Docker 上跑，不碰云端。`threadpilot/.env` 填好 `OPENAI_API_KEY`，并加一行 `CHAT_REQUESTS_PER_MINUTE=0`（评测时关闭每分钟限额），
然后按 [evaluation.md](evaluation.md)（"Results: the live backend"）：

```
grep BUSINESS_NOW .env          # 应输出 BUSINESS_NOW=2026-04-01T08:00:00+08:00
docker compose up -d --build
python3 -m evaluation.run_backend --first-pass --save backend_first_run
```

把生成的 `backend_first_run.json` 发给 Matthew。只跑一次、报告第一次的结果。
