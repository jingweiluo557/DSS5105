# HTTP cloud function deployment

The maintained English deployment guide is [docs/CLOUD_DEPLOYMENT.md](../../docs/CLOUD_DEPLOYMENT.md). Follow its database migration, credential, timer and public SSE acceptance steps before deploying.

## Files

| File | Purpose |
|---|---|
| `export_requirements.py` | Select Linux Python 3.11 requirements from the exported lock |
| `requirements-linux311.txt` | Target dependency list |
| `scf_bootstrap` | Executable Linux HTTP bootstrap, port 9000 |
| `package.py` | Allowlisted backend package plus separate timer archives |
| `timer.py`, `index.py` | Reminder timer function |
| `morning_timer.py` | Morning report timer function |

Build from the application root after installing compatible dependencies into `.build/cloud-function-full`:

```sh
python deploy/cloud-function/export_requirements.py
python deploy/cloud-function/package.py
```

Outputs go to ignored `dist/`. They contain no application `.env` or local workflow database. The current database migration head is `0008_ai_morning`; migrate using the repository before startup. Function startup does not migrate or import sample data. An archive passing structural checks still requires verification on the intended Linux runtime and public gateway.
