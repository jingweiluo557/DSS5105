# Cloud deployment and operations

This repository supports a persistent container service or an HTTP cloud function with a separately hosted static frontend. Code compatibility and packaging checks are distinct from acceptance on an actual cloud gateway; consult [RELEASE_VALIDATION.md](RELEASE_VALIDATION.md) for the current evidence.

## Database and configuration

The selected database provider for this deployment is **CloudBase SQL database (MySQL)**. Enable its direct-connection service and use SQLAlchemy/PyMySQL with the actual database name and port from the console (do not assume the database is named `threadpilot`). Configure the HTTP function's VPC access and use the internal endpoint at runtime; an external endpoint is for local migration/debugging only. The migration connection and runtime connection may have different hosts and ports. See the [CloudBase-specific walkthrough](CLOUDBASE_STEP_BY_STEP_ZH.md) and [official direct-connection documentation](https://docs.cloudbase.net/database/configuration/db/tdsql/direct-connection). Existing backend code uses the MySQL protocol; this choice does not require switching to the CloudBase document-database SDK.

Use MySQL 8 with persistent storage. Back up the existing database before a schema upgrade. From `backend`, run `python -m alembic upgrade head` with a migration-capable `DATABASE_URL`; verify `python -m alembic current` reports `0008_ai_morning`. Runtime application credentials need SELECT/INSERT/UPDATE/DELETE, not schema administration. `scripts.provision_mysql` is for controlled account provisioning and resets the named users' grants/passwords; do not run it casually against an existing shared deployment.

Use a separate read-only `AI_DATABASE_URL` restricted to orders, production_log and workshops. URL-encode connection credentials. Do not import seed data into an existing live database. Migrations are not automatically applied by `scripts.serve` or `scripts.cloud_serve`.

| Setting | Cloud use |
|---|---|
| `DATABASE_URL` | Shared application database with current migrations |
| `AI_DATABASE_URL` | Separate SELECT-only connection for SQL assistant |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | Server-side model credentials and endpoint; never frontend values |
| `INTENT_API_STYLE` | `responses` or supported `chat_completions` provider mode |
| `WORKFLOW_STORAGE` | `database` for shared persisted sessions/actions/reminders |
| `API_ACCESS_TOKEN` | Shared workspace access; frontend sends `X-ThreadPilot-Token` |
| `DATA_API_TOKEN` | Separate data-administration credential, not a manager-review token |
| `SCHEDULER_TOKEN` | Separate bearer token for internal timer endpoints |
| `BUSINESS_NOW` | `live`; use a fixed timezone-aware date only for replay |
| `CORS_ORIGINS` | JSON list of exact frontend origins when separately hosted |
| `SERVE_FRONTEND` | true for one-origin container; false for backend-only function |
| `BACKGROUND_TASKS_ENABLED` | true for one persistent scheduler process; false for functions/external triggers |
| `MORNING_SCHEDULER_ENABLED` | false by default; explicitly enable for persistent in-process morning generation |
| `SYNC_ENABLED` | false for functions; no durable local file watcher |
| `CHASE_WEBHOOK_URL`, `CHASE_WEBHOOK_TOKEN`, `REPLY_INGEST_TOKEN` | Optional real messaging integration; leave unconfigured until tested |

Application, data and scheduler tokens must be distinct. HTTP cloud startup enforces this and requires database/model settings. The shared access token does not establish individual manager identities. Use private networking, HTTPS and suitable access controls for the intended audience.

## Container path

The Dockerfile uses Python 3.12 and an unprivileged runtime user. The Compose stack provisions MySQL and starts the backend after successful migration. `WORKFLOW_STORAGE` defaults to database in Compose; existing installations using a SQLite workflow volume must keep `WORKFLOW_STORAGE=sqlite` until they deliberately migrate history (no automatic history transfer is implemented).

```sh
docker compose config --quiet
docker compose up --build -d
```

Configure root `.env` first, using `.env.example`. The backend port is published on loopback, suitable behind an HTTPS proxy. Docker volumes retain MySQL and any legacy SQLite workflow data. Configure platform health checks against `/api/v1/health`. Backups, restore verification and secret rotation are deployment responsibilities.

The image carries sample CSVs for explicit demo initialization. Local credentials, runtime databases, dependency/build directories and archives are excluded from the build context. Do not copy a local acceptance database into the image.

## HTTP cloud function path

The existing bootstrap targets Linux x86_64 Python 3.11 at `/var/lang/python311/bin/python3.11`, with code at `/var/user` and HTTP port 9000. Match those runtime paths on the target platform or adapt the bootstrap; this is not a portable zip for arbitrary providers.

1. Export target requirements with `python deploy/cloud-function/export_requirements.py`.
2. Install those requirements into `.build/cloud-function-full` in a matching Linux Python 3.11 environment. Cross-platform wheel downloads must use Linux-compatible wheels; Windows installed packages are not suitable.
3. Run `python deploy/cloud-function/package.py`. It produces the backend ZIP and separate reminder/morning timer ZIPs in `dist/`, checks archive integrity, executable bootstrap and exclusion of local runtime/env files.
4. Apply database migrations separately from the repository. The function archive intentionally does not contain Alembic migrations.
5. Configure secrets in the cloud environment, upload the backend artifact, and configure HTTP routing and outbound database/model connectivity. Do not commit private configuration files.
6. Set the timer functions' HTTPS `BACKEND_ORIGIN` and scheduler token. The reminder timer calls `/api/internal/reminders/run`; the morning timer calls `/api/internal/briefings/run`. Configure the latter at/after 07:00 Asia/Shanghai. Do not rely on background loops inside an ephemeral function.

## CloudBase frontend connected to Git

The intended release path is a manually uploaded backend ZIP and a frontend connected to branch `codex/queue-risk-expedite`. Docker is optional and is not required for this path.

In CloudBase's Git application deployment, select the DSS5105 repository and this branch. Configure:

| Field | Value |
|---|---|
| Application/root directory | `threadpilot` |
| Framework | Static/custom |
| Install command | None (no npm packages required) |
| Build command | `node deploy/build_frontend.cjs` |
| Output directory | `dist/frontend` (relative to `threadpilot`) |
| Deployment path | `/` on the selected frontend site |
| Build environment variable | `THREADPILOT_PUBLIC_API_BASE=https://YOUR-BACKEND-ORIGIN` |

If the platform runs commands from the repository root instead, use `node threadpilot/deploy/build_frontend.cjs` and output `threadpilot/dist/frontend`. The build script copies public frontend assets and injects the configured HTTPS backend origin into the output only. It rejects missing, loopback, insecure and malformed origins, preventing an apparently successful deployment that calls the wrong backend. No API key, database password or access token belongs in build variables or frontend files.

Set the backend's `CORS_ORIGINS` to the actual CloudBase frontend HTTPS origin. Enter the shared application token through the workspace UI when enabled. Publish the complete output directory so both `index.html` and `briefing.html` are available. Future Git pushes may trigger a frontend deployment once the repository integration is enabled; verify backend API compatibility before those pushes.

CloudBase supports Git source deployment, custom build commands and build-time environment configuration; see its official [deployment guide](https://docs.cloudbase.net/hosting/web-hosting) and [hosting configuration](https://docs.cloudbase.net/cli-v1/hosting). The values above are this project's configuration, not a claim that a cloud project has already been connected.

## Frontend and streaming

For a single-origin deployment, leave `frontend/config.js` apiBase empty. For static hosting such as GitHub Pages, set it to the public HTTPS backend origin and allow the exact frontend origin in CORS. Static hosting cannot run Python or MySQL. Test the workspace and `/briefing.html` from another device; neither should call that device's localhost.

Disable proxy buffering for SSE, retain keep-alive comments and choose request timeouts that allow planning, tool queries and model generation. Verify multiple text chunks through the real public endpoint; local streaming does not prove gateway streaming. Serve HTML/JS/CSS with revalidation so clients receive new releases.

## Release checklist and rollback

- Confirm migrations at head, AI read-only grants and a restorable database backup.
- Verify authenticated health/data/chat, unauthorized rejection, draft conflicts and duplicate-confirmation behavior.
- Restart the service and verify persisted conversations/drafts/actions. Test concurrent access on the actual shared database.
- Generate a real grounded morning report and verify timer execution, deduplication and failure reporting.
- Verify streamed text, CORS and same-backend access from desktop and mobile through HTTPS.
- Test chase delivery/reply ingestion with a designated recipient if that integration is enabled.
- Keep the previous application artifact and configuration. Roll back application code only when schema-compatible; otherwise restore the verified backup or apply a reviewed forward repair. Do not blindly downgrade a database with new user records.

No production deployment, public gateway check, or production database migration is implied by a successful local package build.
