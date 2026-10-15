# Backend

FastAPI application with SQLAlchemy persistence, deterministic planning tools and OpenAI-compatible conversation generation. Supported Python: 3.11–3.13.

From the repository application directory, run `uv sync --project backend --frozen`. Configure `backend/.env` from its example; do not put administrative database credentials into the running application. From `backend`, use:

```sh
python -m scripts.provision_mysql       # new/local MySQL provisioning, administrator credentials required
python -m scripts.init_db --seed-existing --skip-migrate  # optional demo data only
python -m scripts.serve                # HTTP server, PORT defaults to 8000
```

Use the virtual environment created by uv, or prefix commands with `uv run --frozen`. For existing deployments, run `python -m alembic upgrade head` with migration credentials before restarting the application. The current head is `0008_ai_morning`.

The interactive API contract is `/docs`; `/openapi.json` is generated from current Pydantic models. [API_DOCUMENTATION.md](API_DOCUMENTATION.md) is an older detailed reference and may describe historical behavior. Current additions and operational behavior are documented in the [tool specification](../docs/TOOL_SPECIFICATION_SPRINT1.md), [SSE contract](STREAMING_API.md), and [cloud guide](../docs/CLOUD_DEPLOYMENT.md).

For cloud instances, use `WORKFLOW_STORAGE=database`. Local SQLite workflow storage is intended for one persistent process. A model key is needed for generated narrative and morning reports; core deterministic workflows provide a basic fallback when the conversation model is unavailable.
