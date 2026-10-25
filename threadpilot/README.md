# ThreadPilot

Cloud email release: see [deployment checklist](docs/CLOUDBASE_RELEASE_20261024.md).
Settings now manages the advancing business clock, Outlook connection and email
recipients. Reviewed chase-up emails and 07:00 briefings persist in shared MySQL
when `WORKFLOW_STORAGE=database`; Activity Log displays submission results.

A factory management workspace for order lookup, shared queue-risk analysis, expedite impact reviews, AI conversations, and grounded morning briefings. The application reads the current database snapshot; historical CSV files are seed inputs, not a live production feed.

## Evaluation (Sprint 2)

`evaluation/` holds the Track 1 deliverable: 47 questions with answers computed from the CSVs by code, an automatic scorer with an invented-number check, the 24 Oct 2026 live first pass (29/47, 0 untraced numbers) and the failure analysis that drove the Sprint 2 fixes. `python evaluation/run_annotated_eval.py` replays all 47 questions through the server offline in seconds. See [evaluation/README.md](evaluation/README.md), the one-table [docs/TOOL_SPECIFICATION.md](docs/TOOL_SPECIFICATION.md), [docs/PREDICTION_MODEL.md](docs/PREDICTION_MODEL.md), [docs/ALERT_POLICY.md](docs/ALERT_POLICY.md), [docs/VAGUE_QUESTIONS_AND_DIALOGUES.md](docs/VAGUE_QUESTIONS_AND_DIALOGUES.md) [docs/NO_ARITHMETIC_PROOF.md](docs/NO_ARITHMETIC_PROOF.md), [docs/BUSINESS_CASE.md](docs/BUSINESS_CASE.md), [docs/SPRINT1_EVIDENCE.md](docs/SPRINT1_EVIDENCE.md) and the [CEO interface review](docs/CEO_INTERFACE_REVIEW.md) behind the home screen. CI runs the test suite and the offline evaluation on every push.

## Current capabilities

- English AI answers, bounded multi-request planning, topic switching and resumption, and live text streaming.
- Shared risk and expedite calculations with the same orders, working calendar and capacity estimates.
- Manager-reviewed schedule changes, editable review-reason drafts, chase-up previews, notes and conditional reminders.
- Database-grounded AI morning reports, archived evidence and concise dashboard bullets. Model failures are reported instead of inventing a report.
- Same-origin frontend networking for local, LAN and cloud use, with optional separate HTTPS backend configuration.

## Quick start

Python 3.11–3.13 is supported. MySQL 8 is the intended shared deployment database. SQLite is also used by isolated acceptance tests. Install dependencies with `uv sync --project backend --frozen` or `python -m pip install -r requirements.txt`.

1. Copy `backend/.env.example` to `backend/.env`, then configure the database URLs and model credentials. Never commit credentials.
2. For a new local MySQL database, set `MYSQL_ROOT_PASSWORD` in the provisioning process and run `python -m scripts.provision_mysql` from `backend`. This creates the schema and separate application and read-only AI accounts. Use a migration-capable account for future schema upgrades.
3. From `backend`, explicitly import the sample dataset with `python -m scripts.init_db --seed-existing --skip-migrate` after provisioning. Do not seed an existing production database.
4. Run `python -m scripts.serve` from `backend`; open http://127.0.0.1:8000. The server binds to all interfaces. Set `BUSINESS_NOW=live` for actual operation; a dated, timezone-aware value is only for dataset replay.

For Docker Compose, copy the root `.env.example` to `.env`, replace passwords and tokens, and run `docker compose up --build -d`. Provisioning migrates the database but does not import sample orders: explicitly run `docker compose exec backend python -m scripts.init_db --seed-existing --skip-migrate` for a new demo database. The published port is loopback-only; expose it through an authenticated HTTPS reverse proxy for cloud use.

## Documentation

- [Documentation index](docs/README.md)
- [Tool specification (English)](docs/TOOL_SPECIFICATION_SPRINT1.md)
- [Conversation and streaming](docs/CONVERSATION_UPGRADE.md), [SSE contract](backend/STREAMING_API.md)
- [Queue analysis and manager review](docs/QUEUE_SCHEDULING.md)
- [Morning reports and frontend networking](docs/AI_MORNING_AND_NETWORK.md)
- [Cloud deployment and operations](docs/CLOUD_DEPLOYMENT.md)
- [Release validation](docs/RELEASE_VALIDATION.md)

## Repository map

| Directory | Responsibility |
|---|---|
| `backend/app` | API, conversation orchestration, deterministic tools and services |
| `backend/tests` | Isolated backend regression tests |
| `frontend` | Static management workspace; no frontend build required |
| `data/migrations` | Alembic schema history; current head `0008_ai_morning` |
| `data/dictionary` | Dataset schemas and validation rules |
| `deploy/cloud-function` | Linux Python 3.11 backend and timer packaging |
| `tests/e2e` | Browser regression checks |

## Validation and limits

Run `python -m pytest backend/tests -q` from this directory using the backend environment. Real MySQL integration requires a dedicated `threadpilot_test` database via `TEST_MYSQL_URL`. Browser checks use Playwright and Microsoft Edge; see the validation report for the checks actually executed.

Risk estimates are forecasts, not delivery promises. Monetary value, customer priority and penalty costs are not used in expedite scoring. Applying a review changes ThreadPilot dispatch priority, not an external ERP. External chase delivery requires a real gateway and receipt. Shared access tokens are not individual identity or tenant isolation. Cloud packaging and isolated tests do not establish live cloud deployment readiness by themselves; complete the deployment checklist before opening access.
