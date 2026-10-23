# Documentation

These English guides describe the current implementation. The filename of the tool specification is retained to preserve existing links; its content covers the current release, not only Sprint 1.

| Guide | Contents |
|---|---|
| [Project README](../README.md) | Setup, repository layout and scope |
| [Tool specification](TOOL_SPECIFICATION_SPRINT1.md) | Inputs, outputs, failure modes, evidence and confirmation boundaries |
| [Conversation architecture](CONVERSATION_UPGRADE.md) | Multi-turn state, tools, fallback and streaming |
| [SSE contract](../backend/STREAMING_API.md) | Request/event format, cancellation and reverse proxy requirements |
| [Queue scheduling](QUEUE_SCHEDULING.md) | Risk, expedite comparison and manager review drafts |
| [Morning reports and networking](AI_MORNING_AND_NETWORK.md) | Grounding, concise presentation and backend origin selection |
| [Personal Outlook connection](OUTLOOK.md) | OAuth setup, local connection page, confirmed sending and troubleshooting |
| [Cloud deployment](CLOUD_DEPLOYMENT.md) | Database migrations, configuration, packaging and release checklist |
| [Release validation](RELEASE_VALIDATION.md) | Checks executed and unverified deployment conditions |

The running `/docs` and `/openapi.json` are authoritative for HTTP request schemas. Source code and regression tests determine actual behavior when an older guide differs.


For step-by-step console operations in Chinese, see the [CloudBase deployment walkthrough](CLOUDBASE_STEP_BY_STEP_ZH.md).

## Historical references

Earlier Chinese guides and evaluation reports are retained for context: [user manual](USER_MANUAL.md), [intent workflows](INTENT_WORKFLOW.md), [data pipeline](data_pipeline.md), and [frontend notes](../frontend/README_ZH.md). They are not current cloud acceptance evidence. Historical model test results must retain their date, dataset and failure counts; do not combine successful retries into a claimed single-run pass rate.
