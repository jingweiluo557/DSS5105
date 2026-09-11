# 前端流式测试

测试自建本地 mock SSE 服务，不请求 OpenAI，也不要求后台启动。

```powershell
cd tests/e2e
npm install
npm test
```

需要 Node.js 与 Microsoft Edge（channel=msedge）。安装后生成的 package-lock.json 应随团队实际版本提交。

覆盖增量在完成前可见、完整结果与订单上下文、停止、重试、新会话取消。后端协议另由 backend/tests/ 验证。
