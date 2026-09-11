# 团队协作约定

## 环境

按 [README](README.md) 使用 uv sync --locked；从 backend/.env.example 创建本地 .env。提交 pyproject.toml、uv.lock，不提交 .env、.venv。已添加根目录 .gitignore，但它不会自动取消已被 Git 跟踪的文件。

## 分支与 PR

从主分支创建 feat/功能、fix/问题 或 docs/主题分支。完成后提交 PR，请队友检查再合并。PR 说明问题、修改后的行为、受影响接口与页面、验证结果，以及是否要同步依赖或更新配置。

本次没有新增 CI 或 GitHub 分支保护；检查在本地执行。

## 接口修改

1. 更新 backend/app/ 与调用方。
2. 更新 backend/tests/，运行 uv run --locked pytest -q。
3. 更新 backend/API_DOCUMENTATION.md 的字段、SSE 事件和错误语义。
4. 在 backend 运行 uv run --locked python -m scripts.export_openapi，提交 docs/openapi.json。
5. 破坏兼容时在 PR 写明迁移方式，不静默改变 delta/done 或字段类型。

OpenAPI 与 Markdown 随同一个 PR 更新；Apipost 导入后检查实际 Base URL。统一部署前，每位成员运行自己的本地服务。

## 数据与测试

源 CSV 维护于 data/。修改后在 backend 运行 scripts.build_frontend_data，提交 frontend/data.js，并核对页面和后端一致。

流式 UI 修改运行 tests/e2e 的 mock 测试。scripts.smoke_stream 与 smoke_live 会调用真实 API，手动按需执行。错误报告和截图不包含 Key。

archive/ 只用于历史回溯，不运行其中的旧升级脚本来维护当前应用。
