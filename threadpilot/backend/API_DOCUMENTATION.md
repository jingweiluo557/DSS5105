# ThreadPilot AI API · v1.1.0

当前网页使用 **POST /api/v1/chat/stream**，通过 SSE 边生成边显示英文回答。非流式接口保留兼容。本文对应 backend/app/ 中的实现。

## 1. 启动与链接

在项目根目录打开 PowerShell：

```powershell
cd backend
uv sync --locked
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

配置为 backend/.env，参考 [.env.example](.env.example)。修改后重启；系统同名环境变量优先。旧 main:app 命令兼容保留。

| 入口 | 链接 |
|---|---|
| AI 页面 | [AI Co-Pilot](http://127.0.0.1:8000/#/ai) |
| 驾驶舱 | [Dashboard](http://127.0.0.1:8000/#/dashboard) |
| 交互文档 | [Swagger](http://127.0.0.1:8000/docs) |
| 阅读版 | [ReDoc](http://127.0.0.1:8000/redoc) |
| 在线接口定义 | [OpenAPI JSON](http://127.0.0.1:8000/openapi.json) |
| GitHub 中的接口定义 | [docs/openapi.json](../docs/openapi.json) |

Base URL：`http://127.0.0.1:8000`。每位队员的 127.0.0.1 指向自己的电脑；GitHub 不会自动托管 API。团队部署后再替换 Base URL。当前未实现应用登录鉴权或服务端多用户同步。

## 2. 接口总览

| 方法 | 完整 URL | 成功类型 |
|---|---|---|
| GET | http://127.0.0.1:8000/api/v1/health | application/json |
| POST | http://127.0.0.1:8000/api/v1/chat/stream | text/event-stream |
| POST | http://127.0.0.1:8000/api/v1/chat | application/json |

聊天请求使用 Content-Type: application/json。流式请求建议加 Accept: text/event-stream。
浏览器不传 OpenAI Key、model 或 stream 参数。允许跨域来源为 localhost / 127.0.0.1 的 8000、8765 端口。

## 3. GET 健康检查

```powershell
curl.exe http://127.0.0.1:8000/api/v1/health
```

HTTP 200 示例：

```json
{"status":"ok","configured":true,"model":"gpt-4.1","streaming":true}
```

不需要 Body、认证 Header；不调用模型。configured 仅表示启动时创建了 API 客户端，**不验证 Key、额度、模型权限或数据完整性**。

## 4. 共用请求体

两个聊天接口使用相同 JSON：

```json
{
  "message": "Why is the second order at risk?",
  "history": [
    {"role": "user", "content": "Only show TrendCart orders."},
    {"role": "assistant", "content": "The first two orders are ORD-120 and ORD-020."}
  ],
  "context": {
    "page": "ai",
    "selected_order_id": null,
    "visible_order_ids": ["ORD-120", "ORD-020"]
  }
}
```

| 字段 | 必填 | 类型、默认和约束 |
|---|---|---|
| message | 是 | string；去掉首尾空白后 1–1500 字符 |
| history | 否 | 默认 []；最多 20 条，时间升序，不含本次 message |
| history[].role | 是 | user / assistant；不允许 system / developer |
| history[].content | 是 | string；每条 1–12000 字符，总历史最多 60000 字符 |
| context | 否 | 默认空上下文 |
| context.page | 否 | string；默认 ai，最多 60 字符，不是枚举 |
| context.selected_order_id | 否 | 默认 null；否则为存在的 ORD-三位数字 |
| context.visible_order_ids | 否 | 默认 []；最多 120 个真实订单 ID，保留显示顺序 |

所有请求模型拒绝额外字段，包括 stream。指代“第二张”需传上一轮实际有序列表；示例 selected_order_id 使用 null，避免与明确选中订单冲突。

后端不保存 conversation_id 或历史。每轮由调用方传完整的最近历史；未完成预览不能作为成功 assistant 答案传入。

## 5. SSE 协议

建立连接返回 HTTP 200，Content-Type: text/event-stream，响应头包含 Cache-Control: no-cache、X-Accel-Buffering: no、X-Request-ID。

每个事件由空行分隔，data 是独立 JSON。网络 chunk 不等于 SSE 事件边界。

| event | data 字段 | 前端行为 |
|---|---|---|
| start | request_id, model | 记录身份，进入生成状态 |
| delta | text | 追加增量纯文本到预览 |
| done | 完整回答对象，见下表 | 校准最终文字、保存正式历史、显示订单/证据操作 |
| error | code, message, request_id | 标记失败，保留不完整预览，允许人工重试 |

正常：start → 零个或多个 delta → done。
失败：start → 若干 delta → error；取消或网络故障也可能直接断开，没有终止事件。

**只有 done 表示完整成功，HTTP 200 或出现文字都不代表回答成功。**

协议示例（不是实测模型结果）：

```text
event: start
data: {"request_id":"demo-request","model":"gpt-4.1"}

event: delta
data: {"text":"The dataset business date is "}

event: delta
data: {"text":"April 1, 2026."}

event: done
data: {"answer":"The dataset business date is April 1, 2026.","order_ids":[],"selected_order_id":null,"sources":[],"request_id":"demo-request","model":"gpt-4.1","business_date":"2026-04-01","usage":null}

```

delta 可包含一个或多个字符，不是固定速度的打字动画。后端仅暴露 answer 字段的增量，不暴露未完成结构化 JSON。订单引用在最终校验后才用于操作。

### 完整回答字段

done 的 data 与非流式成功 JSON 相同：

| 字段 | 含义 |
|---|---|
| answer | 完整英文纯文本；用 textContent 或转义 HTML 显示 |
| order_ids | 去重的有效订单 ID，最多 10 个，保持顺序 |
| selected_order_id | 明确解释的订单 ID，或 null |
| sources | 模型声明使用的文件，仅 orders.csv / production_log.csv / workshops.csv |
| request_id | 请求 ID，与 X-Request-ID 对应 |
| model | 最终上游模型名，可能包含具体版本 |
| business_date | 固定 2026-04-01 |
| usage | input_tokens、output_tokens、total_tokens 整数；未提供为 null |

sources 是文件级声明，不是逐句自动核实的引用。

### 客户端实现与取消

参考 [frontend/ai-stream.js](../frontend/ai-stream.js)。使用 POST fetch、ReadableStream 和流式 TextDecoder；缓冲至完整事件再 JSON.parse。原生 EventSource 不适合这里的 POST JSON 请求。

Stop generating 使用 AbortController。停止、断连、新会话后，局部文字不提交为正式答案，迟到结果被忽略。重试是新请求，不支持续传、Last-Event-ID 或幂等去重。

SDK 超时由 OPENAI_TIMEOUT_SECONDS 控制，默认 60 秒；流处理总时限 180 秒；当前浏览器连续 90 秒未收到数据会取消。没有心跳事件，SDK 自动重试关闭。取消不能保证上游完全停止计费。

## 6. 错误处理

### 流开始前：非 200 JSON

| HTTP | code / 格式 | 原因 |
|---|---|---|
| 503 | API_KEY_NOT_CONFIGURED | 未配置 Key |
| 503 | DATA_UNAVAILABLE | 源数据读取或解析失败 |
| 413 | HISTORY_TOO_LARGE | 历史总长度超限 |
| 422 | UNKNOWN_ORDER | 上下文引用不存在的 ID |
| 422 | FastAPI detail 数组 | 必填、类型、长度、额外字段等校验失败 |

应用错误：

```json
{"error":{"code":"API_KEY_NOT_CONFIGURED","message":"Set OPENAI_API_KEY in backend/.env and restart the backend.","request_id":"..."}}
```

字段校验错误使用 `{"detail":[...]}`，调用方需兼容两种结构。

### 流开始后：HTTP 200 内的 error 事件

```text
event: error
data: {"code":"MODEL_QUOTA_EXCEEDED","message":"OpenAI API credits are exhausted. Check API billing and add credits before retrying.","request_id":"..."}

```

| code | 原因 |
|---|---|
| MODEL_TIMEOUT | SDK 或流总时限超时 |
| MODEL_RATE_LIMITED | 上游 HTTP 429，限流或额度问题 |
| MODEL_QUOTA_EXCEEDED | 上游已经打开的流明确报告额度耗尽 |
| MODEL_CONNECTION_ERROR | 连接模型失败或中断 |
| MODEL_API_ERROR | 上游拒绝或其他 API 错误 |
| INVALID_MODEL_RESPONSE | 空答案、未完成或无有效结果 |
| INVALID_MODEL_REFERENCE | 模型引用不存在的订单 |
| MODEL_RESPONSE_ERROR | 其他解析或生成异常 |

相同额度问题可能因上游错误形式不同返回 MODEL_RATE_LIMITED 或 MODEL_QUOTA_EXCEEDED。上游异常原文和密钥不返回浏览器。

## 7. 非流式兼容接口

POST http://127.0.0.1:8000/api/v1/chat，使用第 4 节请求体，一次返回完整回答对象，不返回 SSE 事件。

请求校验错误与流式接口相同；模型错误通过 HTTP 429（MODEL_RATE_LIMITED）、504（MODEL_TIMEOUT）或 502（连接/API/无效响应/无效引用/解析错误）及 error 对象返回。

## 8. Apipost 与 curl 联调

1. 先测试 GET 完整地址 http://127.0.0.1:8000/api/v1/health，清空示例 Body 和多余 Header。
2. 导入 [OpenAPI 文件](../docs/openapi.json) 或在线 /openapi.json。定义包含本地 servers 地址；导入后核对实际请求 URL。
3. 流式请求选择 POST，地址填写 http://127.0.0.1:8000/api/v1/chat/stream，Body 选择 JSON，使用第 4 节示例。
4. 若接口工具缓冲至结束才显示，使用网页或 curl 验证实时效果；Swagger 的展示节奏不是验收标准。

在项目根目录运行（需先启动后端，会调用真实模型）：

```powershell
curl.exe -N -X POST "http://127.0.0.1:8000/api/v1/chat/stream" -H "Content-Type: application/json" -H "Accept: text/event-stream" --data-binary "@docs/examples/chat-request.json"
```

404 时检查协议、主机、8000 端口、路径及“实际请求”。只填 /api/v1/health 需要工具已设置正确 Base URL。不要把 #/ai 放入 API 地址。方法不匹配通常为 405。返回 HTML 时可能请求了静态服务或其他主机。

## 9. 数据与功能边界

- 后端每次读取根目录 data/ 三份 CSV，重算风险规则与产量摘要；前端读取 frontend/data.js 生成快照。
- 数据业务日期固定 2026-04-01；产量日志截至 2026-03-31，没有实时工厂连接。
- 小数据集整体及问题会发给模型；风险分数为启发式规则，不是预测概率。
- 模型仅回答和起草，没有发送消息、修改 CSV、后台监控或分配车间工具。
- OPENAI_MODEL 默认 gpt-4.1；OPENAI_MAX_OUTPUT_TOKENS 默认 2500。.env 留本地，仅提交空模板。
- FastAPI 同时托管 / 前端和 /data 源数据；不公开 backend、docs 或 .env。

## 10. 维护与验证

在 backend 运行：

```powershell
uv run --locked pytest -q
uv run --locked python -m scripts.export_openapi
```

离线测试 mock SDK，不消耗 API 额度。前端流式交互测试见 [测试说明](../tests/e2e/README.md)。

接口改动的 PR 同时更新 app/、tests/、本文、docs/openapi.json 与调用方。OpenAPI 表达路径和字段，本文补充 SSE 顺序、错误和取消语义。参见 [协作约定](../CONTRIBUTING.md)。

