# Python 3.11 HTTP 云函数验证包

这个包仅验证 Python 服务、数据库联网和模型调用，不是完整 ThreadPilot 后端。
不执行建表、写数据、业务消息发送或会话持久化。

控制台设置：HTTP 云函数，名称 threadpilot-api-test，Python 3.11，监听端口 9000。
若页面提供内存、超时设置，测试先选 512 MB、120 秒；实际网关超时需部署后验证。
上传项目 `dist/threadpilot-api-test.zip`，不要上传原项目 ZIP 或任何 .env 文件。
压缩包按 Python 3.11 / Linux x86_64 打包依赖，scf_bootstrap 在根目录且带执行权限。

环境变量从本机 backend/.env.cloudbase 对应项复制到控制台（不含 dotenv 外层引号）：

- AI_DATABASE_URL：现有 AI 只读连接字符串
- DATA_API_TOKEN：验证接口访问令牌
- OPENAI_API_KEY：模型密钥
- OPENAI_BASE_URL：模型 HTTPS API 地址
- OPENAI_MODEL：模型名称
- INTENT_API_STYLE：responses 或 chat_completions，与模型服务能力一致

PORT 默认 9000，不必设置。本验证包不使用业务账号 DATABASE_URL。
凭据仅存控制台环境变量，不写进部署包、截图或聊天。

GET /health：公开健康检查，不读取或返回配置，不访问数据库或模型。
POST /verify/database：需要 Authorization: Bearer <DATA_API_TOKEN>，返回三张表行数。
POST /verify/model：同样需要鉴权，只发送固定的“回复 OK”提示，产生少量模型调用费用。
验证调用可以由本机程序读取已保存 token 后发起，无需在浏览器或前端配置 token。
健康检查成功不等于数据库/模型可用；测试完成后删除测试函数或关闭其公网入口。

本地只能验证代码逻辑和压缩包结构；Linux 二进制依赖、云函数出网和网关路由需要实际部署验证。
