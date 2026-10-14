# Database-backed AI morning briefing and cross-device access

The supported morning page is `/briefing.html`. `/briefing` and the former PR demo URL `/demo/briefing_demo.html` redirect to it. The page has no embedded simulation dataset and uses the same `config.js`, authenticated transport and backend as the workspace. Existing PR simulation exports are not live application pages.

## Backend selection

- An empty `THREADPILOT_CONFIG.apiBase` always means the page's origin, including port 8765. No visitor is silently sent to `127.0.0.1` or a fixed cloud deployment.
- Prefer serving the frontend from FastAPI. Windows: `backend/start.ps1 -Lan`; Unix: `backend/start.sh --lan`. Open `http://<server-LAN-IP>:8000` on devices in the same network. The server must be running and its port reachable from that device.
- A standalone frontend on port 8765 must have an API proxy or an explicit backend origin configured before `config.js`; it no longer guesses port 8000. Separate HTTPS deployments require an explicit HTTPS API origin plus the frontend origin in backend `CORS_ORIGINS`.
- Origins containing credentials, paths or queries, remote visitors pointing at loopback, and HTTPS-to-HTTP configurations fail visibly. There is no fallback to a different backend.
- Changing the configured backend clears conversation identity to prevent sending a session or draft identity to another deployment. Draft recovery copies are also scoped to the backend origin.

## Actual model generation

Run `python -m alembic upgrade head` from `backend/`. Revision `0008_ai_morning` adds immutable `ai_morning_reports`; it preserves existing business data and rule-based archived summaries.

`GET /api/morning` lists archived model reports and the current snapshot fingerprint. `POST /api/morning/generate` reads the database under the shared business lock, then sends an evidence packet to the configured model. The packet contains current order identifiers, due dates, stage, pieces, activity dates and queue risk; recorded production dates/output, prior working-day comparisons; and explicit scheduling assumptions. Customer contacts, credentials and financial weights are excluded.

The model produces three analysis sections: production review, priority issue and manager decisions. A fourth section displays the deterministic capacity assumptions and data limitations, explicitly labelled as system calculation rules. Every section must reference valid evidence keys. A second model pass checks whether prose is supported by the facts; at most one corrected generation is attempted. Numeric tokens and order IDs are also checked against the cited evidence. This reduces unsupported claims but does not make model judgments infallible; evidence remains visible for manager review. Final storage checks that the database fingerprint has not changed during generation.

Only successful outputs are archived, with the model name, response identifiers, business date, actual generation time, fact packet and snapshot fingerprint. A matching snapshot on the same generation day reuses its stored report. New snapshots produce new reports, preserving history. Errors never produce a simulated or template report. Reports created before the grounding check was added are explicitly labelled in the history page.

`operations.briefing` routes natural-language requests for a morning/daily report to this same service. The morning page's order chat uses the existing `/api/v1/workflow/chat` contract (`message`, `session_id`), including multi-turn follow-ups. It does not use the PR demo's incompatible legacy payload.

The existing authenticated `/api/internal/briefings/run` and morning loop now call the model service. Scheduled generation runs once after 07:00 UTC+8 for a generation day/business date. The local acceptance launcher keeps this scheduler disabled; opening the page does not automatically spend model calls. Existing dashboard rule previews and old reports remain labelled as database/rule summaries, not AI generation.

Existing email drafts based on old archived summaries remain unchanged. New AI reports are presented in the workspace and morning page; generation does not email anyone or change scheduling.

## Acceptance

1. Verify the displayed backend origin matches the server on desktop and a LAN/mobile-sized browser.
2. Generate a report with the configured model; confirm its model, business date, record coverage and evidence. Replay dates are displayed explicitly.
3. Reload and check the same report is restored. Repeating generation on the same snapshot reuses its record.
4. Ask about an order, then “它会影响谁？” in the morning page; both turns use the same workflow session.
5. With no model key, a provider error, an unsupported claim or a database change during generation, show an error and preserve existing reports.

Implementation follows the existing SDK configuration and [OpenAI structured output documentation](https://developers.openai.com/api/docs/guides/structured-outputs). Neither API keys nor model settings are shipped to the browser.

Validated on 2026-10-14: real `gpt-4.1` review drafting and a shorter follow-up; real morning generation and a separate model grounding pass; morning-page order analysis plus a pronoun follow-up through the real classifier. The local acceptance snapshot has business date 2026-04-01 and production records through 2026-03-31; it is explicitly a replay of stored records, not newly measured factory activity. Automated backend regression passed 114 tests (one MySQL integration test skipped); the final morning/dashboard/contract subset passed 12 tests. Browser checks covered the LAN origin, old demo URL, current API payload, desktop/mobile-sized layouts and dashboard task handling. No physical second device was controlled during these checks.
