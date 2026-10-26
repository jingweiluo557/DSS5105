# Release validation

Date: 2026-10-15 (Asia/Shanghai)

Branch: `codex/queue-risk-expedite`

Target: backend ZIP uploaded to CloudBase; frontend built from the Git branch.

## Executed checks

| Check | Result | Scope |
|---|---|---|
| Complete backend suite | **120 passed, 1 skipped** | Isolated databases and mocked model/integration boundaries |
| API schema export | Passed | `docs/openapi.json` matches runtime schema |
| Dashboard browser regression | Passed | Bullet summaries, English entry, tasks, persistence and mobile layout |
| Conversation browser regression | Passed | Visible text before completion, stable scroll/panel, final cards, stop/retry/new-chat, fonts and mobile layout |
| Morning page browser check | Passed | Local acceptance server, saved report/evidence, English bullet presentation and same backend |
| Backend-origin checks | Passed | Same-origin local/LAN use; reject mixed content, remote loopback and malformed URLs |
| CloudBase static build | Passed | Public HTTPS origin injection, expected assets, invalid-origin rejection |
| Linux dependency inventory | Passed | 85 vendored distributions match the exported target requirements |
| Backend and timer ZIP generation | Passed | Archive integrity, bootstrap permission, source match, no local env/runtime DB or Windows binaries |

The final backend run completed in 51.20 seconds. Two dependency deprecation warnings remain (Starlette/AnyIO and LangChain Community); they did not fail tests. An initial time-dependent morning test was fixed by freezing its wall clock, and the exported schema was refreshed after changing the default draft instruction to English.

The skipped test requires a dedicated MySQL `threadpilot_test` database via `TEST_MYSQL_URL`. Cloud persistence tests in the isolated suite are not a replacement for actual MySQL engine/grant verification.

Browser tests for chat and dashboard use controlled API fixtures. The morning check reads the local isolated acceptance server and its existing report; this release validation did not initiate a new real-model call or external chase delivery. Prior real-model runs are separate historical evidence.

## Local artifacts

- `dist/threadpilot-backend-python311.zip` — 66,699,441 bytes
- `dist/threadpilot-reminder-timer.zip`
- `dist/threadpilot-morning-timer.zip`
- `dist/frontend` — generated static build used for validation; its backend is the test-only `https://api.example.com`. Rebuild with the actual `THREADPILOT_PUBLIC_API_BASE` before deployment.

Backend ZIP SHA-256: `ddf5a1661f15f86bb41df60ef3cb40f4413c06ef795f6dc11a46ba3d7d24a51a`

Build outputs, credentials and local databases are ignored by Git. The separately pre-staged repository-root archive is not part of this release commit.

## Not executed / release conditions

Docker was not started or used, as requested. No live CloudBase deployment, public gateway SSE check, production migration, real MySQL integration run, external timer trigger or actual recipient delivery was performed in this release pass. Linux package compatibility was checked structurally and against dependency versions, not by running the function on Linux.

Before release, complete the [CloudBase deployment checklist](CLOUD_DEPLOYMENT.md): migrate to `0008_ai_morning`, configure persistent database state and separate tokens, set the frontend's public backend origin and exact CORS origin, verify restart recovery, then verify incremental streaming and morning scheduling through the real HTTPS endpoint. These remaining checks are deployment acceptance work, not claimed local successes.
