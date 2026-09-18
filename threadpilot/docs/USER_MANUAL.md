# ThreadPilot 操作手册

> 范围说明：本手册主要描述原驾驶舱和浏览器内模拟交互。新聊天页面已经接入服务端意图工作流、SQLite 备注/提醒及可配置发送网关；下文“浏览器存储”“没有后台监控”“模拟发送”等描述仅适用于原本地操作流程。新聊天的启动、接口、确认和监控行为以 [项目 README](../README.md)、[API 文档](../backend/API_DOCUMENTATION.md) 和 [工作流设计](INTENT_WORKFLOW.md) 为准。

**适用版本：Track 1 数据版 · FastAPI + OpenAI · uv 管理 · 流式回答**  
**使用对象：项目演示人员、管理者及本地开发人员**

本手册对应 `D:\sem1 课程\DSS5102\output\threadpilot-v2` 中的当前代码。界面为英文，本手册用中文说明，并保留页面上的英文按钮名称，方便逐项对照。

## 1. 先了解当前版本

ThreadPilot 用于查看订单、识别需要跟进的问题，并通过 AI 理解源数据。它是本地运行的开发原型。

| 功能 | 当前状态 |
|---|---|
| 页面导航、订单筛选、详情和证据 | 可以操作，使用已提供的 CSV 数据 |
| AI 问答 | 已接入 FastAPI / OpenAI；需要有效 API Key、模型权限及网络 |
| AI 回答方式 | 边生成边显示文字，完整校验后再显示订单操作按钮 |
| 备注、设置、监控记录 | 存储在当前浏览器中 |
| 催办消息 | 可以编辑、预览、人工确认并生成模拟回执；不真实发送 |
| 监控 Watch | 点击 Check now 时检查；没有后台定时监控 |
| 语音入口 | 可编辑转录文本演示；未接入真实麦克风识别 |
| 可行性评估 | 使用公开说明的产能与排队假设；不自动分配车间 |
| 用户登录、多用户同步 | 尚未实现 |

程序测试与模拟模型联调已通过；这不等于你的 API Key、余额与模型权限已经验证成功。应按第 4 节完成首次真实问答。

## 2. 文件位置与入口

| 文件或目录 | 用途 |
|---|---|
| `backend/` | FastAPI 服务与 uv 项目 |
| `backend/.env` | 你自己的 API 配置 |
| `backend/.env.example` | 空配置示例，不是正常运行时读取的配置文件 |
| `backend/pyproject.toml`、`backend/uv.lock` | 依赖声明与锁定版本 |
| `backend/start.ps1` | uv 启动脚本 |
| `backend/API_DOCUMENTATION.md` | 完整接口说明 |
| `docs/openapi.json` | 可导入接口工具的定义 |
| `frontend/` | 前端页面和交互代码 |
| `data/` | 当前使用的源 CSV 与数据字典 |

旧的 `ThreadPilot_Interactive_Track1.zip` 是较早的纯前端交付快照，不包含后续 FastAPI / uv 接入。开发和运行以当前目录为准。

## 3. 配置与启动：第一次使用

### 3.1 打开正确目录

在 PowerShell 中执行：

```powershell
cd "D:\sem1 课程\DSS5102\output\threadpilot-v2\backend"
uv --version
```

出现 uv 版本号说明命令可用。如果提示找不到 uv，先安装 uv，然后重新打开 PowerShell。安装说明：https://docs.astral.sh/uv/getting-started/installation/ 。当前电脑已经检测到 uv，无需重复安装。

### 3.2 配置 API Key 并保存

用编辑器打开 `backend/.env`，填写以下配置；不要把示例占位文字当作真实 Key：

```dotenv
OPENAI_API_KEY=填入你自己的实际Key
OPENAI_MODEL=gpt-4.1
OPENAI_TIMEOUT_SECONDS=60
```

检查以下事项：

1. 文件名确实是 `.env`，不是 `.env.txt` 或 `.env.example`。
2. 变量名为 `OPENAI_API_KEY`，等号后不是空白。
3. 在编辑器中按 **Ctrl+S**，确保内容已经保存到磁盘。
4. 不要在网页输入框中填写 Key，也不需要将 Key 发给助手。
5. 模型默认使用 `gpt-4.1`；如需修改，选择你的 API 项目可用且支持 Responses API Structured Outputs 的模型。

服务启动时读取配置。修改 `.env` 后必须重启服务。若系统环境变量中已经设置了同名项，环境变量优先于 `.env`。

### 3.3 同步依赖并启动

```powershell
uv sync --locked
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

首次同步可能需要下载依赖。出现 `Uvicorn running on http://127.0.0.1:8000` 后，保留这个终端窗口，不要关闭。

也可以使用启动脚本，两种方式任选一种，不要同时执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

无需手动激活 `.venv`。后续启动直接使用 `uv run --locked ...` 或启动脚本即可。

### 3.4 打开页面

| 入口 | 地址 |
|---|---|
| AI Co-Pilot | http://127.0.0.1:8000/#/ai |
| 管理驾驶舱 | http://127.0.0.1:8000/#/dashboard |
| 欢迎封面 | http://127.0.0.1:8000/#/cover |
| 接口调试 | http://127.0.0.1:8000/docs |
| 健康状态 | http://127.0.0.1:8000/api/v1/health |

推荐统一使用 **8000** 入口，FastAPI 会同时提供页面和 API。不必另外启动静态网页服务。

已有的 8765 页面也能调用 8000 后端，但 8765 本身需要另外运行静态服务。直接双击 HTML 可以查看页面；首次接入模型时请使用上面的 HTTP 地址，以减少跨域和浏览器本地文件限制带来的问题。

### 3.5 停止和重启

在运行服务的终端按 **Ctrl+C** 即可停止。更新 Key、模型或其他配置后，再执行启动命令。停止后网页可能仍显示已加载内容，但不能继续完成模型问答。

## 4. 首次验证 AI 是否可用

1. 打开 AI Co-Pilot 页面。
2. 查看输入框下方状态：`OpenAI · 模型名 · Ready` 表示后端已配置客户端；它不是 Key 有效性的最终证明。
3. 输入 `What is the business date of this dataset?`，点击 **Send ↗**。
4. 文字会在生成时逐步显示。等待回答完成后核对日期，应为 **April 1, 2026**。
5. 检查回答下方是否显示模型名称与来源信息。若出现错误，按第 13 节排查。

也可在另一个 PowerShell 窗口中进入 backend，执行一次真实 API 验证：

```powershell
uv run --locked python -m scripts.smoke_stream
```

此命令会产生真实 OpenAI 请求并消耗 API 额度，不建议反复运行。它输出配置状态、模型结果或错误代码，不输出 Key。

## 5. 理解页面上的日期和数字

数据字典把“今天”定义为 **2026-04-01**。不要把电脑日期当作数据业务日期。

| 项目 | 当前源数据 |
|---|---|
| 订单 | 120 个；34 个进行中，86 个已完成 |
| 进行中且逾期 | 8 个 |
| 今日到期 | 1 个 |
| 至少 5 天无活动 | 2 个进行中订单 |
| 工序产量 | 360 行；2026-01-01 至 2026-03-31 |
| 外部车间 | 8 家；7 家 ACTIVE，1 家 SUSPENDED |

工序顺序为 **Knitting → Assembly → Washing → Packing**。周日停工，计算工作日产量均值时排除周日。

Dashboard 中 Assembly 最新产量为 **455 件**，此前 20 个工作日平均 **700.3 件**，下降约 **35.0%**。这是全厂该工序的统计，不能直接说明某张订单完成了多少或停止了生产。

这组数据是固定快照，没有自动实时更新。部分订单活动日期为 4 月 1 日，而产量日志截止 3 月 31 日，两类数据覆盖日期不同。

## 6. Dashboard：从今日重点开始

1. 点击左侧 **Dashboard**。
2. 先读晨间摘要，再查看 **Today’s action queue**。
3. 点击 KPI 卡片进入对应订单列表，例如 **Overdue** 显示正在进行且已经逾期的订单。
4. 点击订单编号或 **Review facts →** 打开详情。
5. 在 **Production pulse** 中选择工序，比较趋势和均值。
6. 点击 **Inspect stage records**，展开对应工序的原始产量记录。

页面底部的 **Delivery history** 描述已完成订单的历史早交、按时或晚交结果，不等于当前逾期订单数量。

## 7. Orders：查询订单、查看详情和证据

### 7.1 查询订单

进入 **Orders** 后，可以按以下条件组合筛选：

- 订单号、客户或产品关键词；也可使用顶部全局搜索。
- Status：In progress / Complete。
- Customer、Category、Stage。
- Delivery：Today / Overdue / Next 7 days。
- Priority、Inactivity。

列表每页 15 条，使用 **Previous / Next** 翻页；**Clear** 清除筛选。当前选择 In progress 和 TrendCart 应得到 6 张订单。

### 7.2 阅读订单详情

点击订单后，依次查看产品、客户、数量、计划交期、当前工序和最后活动日期。已完成订单会显示实际完成日期以及早交或晚交天数，不参与活动订单的风险排序。

四阶段视图表示工序位置，不代表精确完成百分比。源 CSV 没有逐工序事件时间戳，页面不会把工厂总产量伪装成订单活动记录。

### 7.3 添加备注

点击 **Add note** → 输入管理备注 → **Save note**。取消对话框不会保存。备注只存在当前浏览器的本地数据中，不会写回 CSV。

### 7.4 查看证据

点击 **View evidence / Inspect evidence**。证据页包含订单原始字段、CSV 行号、计算口径以及工序日志。可下载完整 CSV 或导出选中记录。

建议先核对原始记录，再把 AI 建议转为实际业务决定。

## 8. Risk Orders 与 Exceptions

**Risk Orders** 仅对 34 个进行中订单排序。点击 **Explain** 后，解释面板更新为该订单，并显示四项得分。

| 因素 | 当前 UI 规则 |
|---|---|
| Inactivity | 无活动日数 × 5，最多 35 分 |
| Due-date pressure | 逾期 35；3 天内到期 28；7 天内 20；14 天内 10；其余 0 |
| Remaining stages | 包含当前工序的剩余工序数 × 5，最多 20 |
| Customer exposure | 该客户活动订单占全部活动订单的比例 × 10，四舍五入 |

总分 ≥80 为 Severe；60–79 为 Warning；低于 60 为 Watch。该评分是可解释的项目规则，不是 CSV 自带字段，也不是迟交概率。请展开 **How is the priority score calculated?** 查看口径。

**Exceptions** 可按 All / Severe / Warning / Watch 筛选。选择异常卡片后查看异常解释、相关订单和证据。工序异常下列出的订单只是共享该工序，不能证明这些订单导致了异常。

## 9. AI Co-Pilot：提问与连续追问

### 9.1 两种使用方式

- 独立 **AI Co-Pilot** 页面：适合连续分析。
- 顶部或右下角 **Ask AI**：打开侧边抽屉，在当前页面继续提问。

两者共享当前对话。输入框下方的 **Context** 显示选中订单。连接模型后文字会逐步显示；生成期间可以点击 **Stop generating**。订单卡片和证据按钮在完整回答校验通过后才出现。

如果主动停止或连接中断，已有文字会标为不完整预览，不作为正式答案传入后续对话。点击 **Retry** 可重新生成。网络可能一次带来多个字符，所以不是固定速度的单字动画。

### 9.2 推荐体验流程

依次发送：

```text
Which orders are most at risk?
Only show TrendCart orders.
Why is the second order at risk?
Draft a chase-up for this order.
```

按照当前优先级规则，TrendCart 列表前两张为 **ORD-120、ORD-020**。检查 AI 的顺序和解释是否与证据一致。真实模型输出具有不确定性，如指代不清，直接补充订单号，例如 `Explain ORD-020 using its source record.`。

也可以询问：

```text
How was assembly output yesterday compared with the previous 20 working days?
Which workshops can handle ACCESSORIES, and which are not eligible?
Explain the delivery outcome of ORD-057.
```

### 9.3 回答后的操作

根据返回内容，回答卡片可能提供 **View order、Evidence、Draft chase-up、Create watch**。这些按钮按模型返回且经服务器校验存在的订单 ID 跳转。

模型可以在文字中起草催办，但不会发送消息。**Draft chase-up** 打开现有的基于订单事实的草稿编辑页；不会自动把所有聊天文字复制到消息正文，需要时请自行编辑或粘贴。

### 9.4 新会话、错误和保存范围

- **New conversation** 清空当前会话，适合换问题或重置上下文。
- 出错时查看提示，解决原因后点击 **Retry**。重试会再发起 API 请求。
- 每次向后端发送最近最多 20 条对话及当前结果列表；长期上下文不是无限保留。
- AI 恢复历史使用当前标签页会话存储；不要将它当作永久聊天档案。没有跨设备会话同步。
- 输入长度最多 1500 字符；长问题拆分为多次明确追问。

源 CSV 和问题会由后端发给 OpenAI 用于生成答案，产生 API token 用量。当前小数据集完整加入上下文，后续可优化为检索。来源文件名是模型声明使用的文件，不代表每句话都已自动核实。

## 10. Feasibility：新订单可行性比较

1. 进入 **Feasibility**。
2. 选择 TOPS 或 ACCESSORIES，填写件数和期望交期。
3. 根据业务要求勾选是否允许外部车间比较。
4. 点击 **Compare scenarios →**。
5. 比较内部排队估算、外部方案和减少 25% 数量的方案。
6. 点击 **Adjust request** 修改条件后再次比较；可用 **Save scenario** 保存当前情景。

内部方案使用历史日产量和活动订单全量件数估算，源数据没有精确剩余件数，因此不是实际排产承诺。

外部车间重点检查：

- **OldMill / Suspended**：不可接新工作。
- **FreshStart / Batch-limited**：每批上限 300 件，800 件需要分成 3 个单独批次。
- **Category mismatch**：品类不匹配，不作为可用方案。
- Current queue、Pickup / batch、Batch defect chance、Cost / piece：结合时间、质量与费用判断。

费用没有标明币种，不要自行假定为美元。缺陷率是批次发生缺陷的概率，不能直接当作返工件数比例。系统不会自动选择或联系车间。

## 11. 催办、监控与操作记录

### 11.1 生成并确认催办

订单详情或风险面板 → **Draft chase-up** → 填写 **Recipient** → 选择演示渠道 → 编辑正文 → **Preview message**。

预览时核对订单号、接收人、交期和活动日期。点击 **Cancel** 不新增消息；点击 **Confirm simulated send** 后，会生成本地模拟回执和审计记录，不真实发送邮件或聊天消息。

源 CSV 不包含负责人或邮箱，接收人需要人工填写。**Copy** 可复制正文；若浏览器阻止剪贴板访问，按提示选中文字并用 Ctrl+C。

### 11.2 创建和检查监控

活动订单 → **Create watch** → 选择活动间隔阈值 → **Confirm watch**。

进入 **Messages & Watches → Standing watches**，点击 **Check now**，按固定业务日期检查阈值；**Pause / Resume** 控制是否允许手动检查。关闭页面后不会有后台通知。

### 11.3 查看回执和审计

- **Demo receipts**：查看已确认的模拟消息。
- **Saved assessments**：查看保存的可行性情景。
- **Activity Log**：按操作类型筛选、展开详情或 **Export audit JSON**。

审计记录保存在浏览器中，包含真实操作时间；它与固定数据业务日期是两种时间概念。本地记录不是防篡改的服务端审计系统。

## 12. Settings 与本地数据

在 **Settings** 中调整晨报时间偏好、默认活动间隔阈值和语音偏好，点击 **Review changes**，核对后确认。

这些设置只保存偏好，不启动后台任务或真实语音识别。**Reset local actions & preferences** 会要求确认，并清除当前浏览器的备注、监控、模拟消息、评估、审计和会话等演示状态；不会删除源 CSV 或 `.env`。

`127.0.0.1:8000`、`localhost:8000`、8765 和本地文件地址的浏览器存储可能分别独立。请固定使用同一个入口，避免误以为记录丢失。更换浏览器、隐私模式或清理网站数据，也可能使本地记录不可恢复。

若要更新数据，请修改根目录 `data/` 的 CSV，然后在 backend 执行 `uv run --locked python -m scripts.build_frontend_data`，重建 `frontend/data.js` 并核对页面与后端一致。

流式请求建立后 HTTP 为 200，中途错误通过 `error` 事件返回；下面 HTTP 错误状态仅适用于流建立前或非流式接口。只有 `done` 才代表完整回答。`MODEL_QUOTA_EXCEEDED` 表示流内报告额度耗尽。

## 13. 常见问题排查

| 现象 | 检查与处理 |
|---|---|
| 找不到 uv 命令 | 安装 uv 后重新打开终端，再执行 uv --version |
| uv sync 失败 | 检查网络、缓存目录权限和锁文件是否与项目匹配；保留报错用于排查，不直接删除 `.env` |
| 8000 端口被占用 | 检查是否已经启动本项目；关闭原项目终端中的服务后再启动，不要随意终止不明进程 |
| Backend offline / Cannot reach FastAPI | 确认终端服务仍在运行，访问 /api/v1/health；推荐从 8000 页面进入 |
| API key not configured / HTTP 503 | 确认保存的是 backend/.env，变量值非空，按 Ctrl+S 后重启；不要只修改 .env.example |
| Ready 但发消息失败 | Ready 只表明客户端已配置；继续检查 Key 有效性、API 项目权限、模型权限和额度 |
| MODEL_RATE_LIMITED / HTTP 429 | 检查 API 额度、计费与请求频率，稍后重试；不要连续点击 |
| MODEL_API_ERROR / HTTP 502 | 检查 Key、OPENAI_MODEL 是否可用，以及该模型是否支持当前响应格式 |
| MODEL_CONNECTION_ERROR / HTTP 502 | 检查后端能否访问 OpenAI 网络服务 |
| MODEL_TIMEOUT / HTTP 504 | 缩短问题或稍后重试；SDK 默认 60 秒，流总时限 180 秒，浏览器连续 90 秒未收到数据会取消 |
| INVALID_MODEL_RESPONSE / INVALID_MODEL_REFERENCE | 没有得到完整合法答案或订单引用，补充明确订单号后重试 |
| HTTP 422 / 请求被拒绝 | 检查问题是否为空、超过长度限制或上下文订单是否存在；可新建会话 |
| “第二张”回答不正确 | 查看上一轮实际列表顺序，直接给出 ORD-xxx，并核对证据 |
| 页面没有使用新配置 | 后端重启后刷新页面；更换模型或 Key 不会自动热更新 |
| 关闭终端后不能问答 | 后端随终端退出；重新启动并保持窗口打开 |

向开发者反馈时，提供错误代码、页面显示的 Request ID、提问内容和操作步骤。不要提供 Key 或未经处理的 `.env` 截图。

## 14. 开发者验证与接口入口

无需真实 Key 的测试：

```powershell
cd "D:\sem1 课程\DSS5102\output\threadpilot-v2\backend"
uv run --locked pytest -q
```

接口检查：启动服务后打开 `/docs`。当前网页使用 **POST /api/v1/workflow/chat/stream**；**POST /chat**（或 `/api/v1/workflow/chat`）返回同一工作流的完整 JSON。首轮示例：

```json
{
  "message": "Why is ORD-002 at risk?",
  "selected_order_id": "ORD-002"
}
```

后续传入响应 `state.session_id` 延续会话；写操作须先预览，再传明确确认文本和 `confirmation_id`。不传客户端 history/context。

点击 **Execute** 会发起真实模型请求，需要已配置 Key。接口不接受浏览器传入 Key、模型名或 `stream` 参数。完整字段、错误码、返回示例见 `backend/API_DOCUMENTATION.md`；机器定义见 `/openapi.json`。

## 15. 五分钟演示顺序

1. **启动与检查**：uv 启动服务，打开 AI 页面，确认可完成一次真实问答。
2. **晨间简报**：Dashboard 展示逾期、停滞和 Assembly 产量变化。
3. **订单证据**：打开 ORD-002，查看活动间隔、风险分解与原始记录。
4. **连续追问**：风险列表 → TrendCart → 第二张订单解释。
5. **行动确认**：打开催办草稿，先取消预览，再确认模拟发送并查看审计。
6. **方案比较**：800 TOPS 的可行性评估，展示暂停车间与 300 件批量上限。

演示时明确说明：AI 已有真实接口；消息外发、后台监控和语音识别仍是开发原型功能。
