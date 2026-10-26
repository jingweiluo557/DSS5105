# Morning reports and backend connectivity

## Grounded generation

Morning reports use the current database snapshot, production records, risk results and capacity context. The model generates three sections: production review, key priorities and manager actions. Priorities and actions contain two to four English bullet points; production review is one or two sentences. A separate model grounding check validates the report against its supplied facts, with one repair attempt. This is a validation layer, not proof that every possible model error is eliminated.

Reports preserve evidence and generation metadata in the database. Cache identity includes generation version, business date and snapshot fingerprint; the current version is `morning-v7-en-bullets`. A changed snapshot is checked before saving. Model failure is surfaced; no fake AI report is substituted. Calculation details are available separately instead of lengthening the dashboard summary.

`POST /api/morning/generate` generates or reuses a matching saved report. Read reports through `/api/morning` and `/api/morning/reports/{id}`. The briefing page intentionally omits backend URLs, report history selection, report IDs, generation timestamps and permanent readiness text. Stored archives remain accessible through the API. It retains model/business date, production date, evidence and actionable status/error messages.

The dashboard shows concise bullets: one production item, up to two priorities and two actions. Its button reads **Full briefing**. Backend-hosted frontend assets revalidate on refresh. For separately hosted CloudBase assets, configure HTML/configuration cache revalidation in the static host/CDN as well.

## Scheduling

In a persistent server, enable `MORNING_SCHEDULER_ENABLED=true` with background tasks enabled. In cloud functions, disable in-process tasks and configure the external morning timer to call `POST /api/internal/briefings/run` with the scheduler bearer token. Scheduled generation checks the 07:00 Asia/Shanghai threshold and saved report state. A stopped process or missing external trigger cannot generate a scheduled report. Business dates and actual generation timestamps are distinct, particularly during dataset replay.

## Networking

`frontend/config.js` defaults to the page's own origin. A phone opening the server's LAN address therefore uses that server rather than the phone's localhost. A separately hosted frontend must set the public `apiBase` to the backend's HTTPS origin and configure its exact frontend origin in backend `CORS_ORIGINS`.

The configuration rejects credentials, paths, queries and fragments in backend origins, remote-browser loopback targets, and HTTP backends from HTTPS pages. Both the workspace and briefing use the same resolution. Never place an OpenAI key or database password in frontend configuration. Application access tokens are scoped to the selected backend.

For cloud operations and SSE gateway checks, see [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md).
