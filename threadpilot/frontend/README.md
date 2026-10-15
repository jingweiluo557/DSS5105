# Frontend

Static HTML, CSS and JavaScript; no framework build or npm dependency installation is required. `index.html` hosts the workspace with hash routes, and `briefing.html` hosts the morning report.

## Local development

The backend serves these files by default. Leave `config.js` apiBase empty to use the page origin on desktop and LAN devices. Configure an explicit backend origin only when hosting the frontend separately. Never put model keys or database credentials in frontend files.

## CloudBase Git deployment

Set the application root to `threadpilot`, build command to `node deploy/build_frontend.cjs`, output directory to `dist/frontend`, and build variable `THREADPILOT_PUBLIC_API_BASE` to the backend HTTPS origin. The script uses Node built-ins only. It preserves the source configuration and writes the selected origin into the generated files. See [the deployment guide](../docs/CLOUD_DEPLOYMENT.md) for root-directory alternatives and CORS settings.

Deploy the entire generated directory. Configure static-host/CDN cache revalidation for HTML and configuration files; the backend's cache middleware cannot control a separately hosted frontend. Verify both the workspace and briefing after each deployment.

## Structure

- `config.js`, `api-client.js`: backend selection and application access.
- `workspace.js`, `chat-layout.css`: workspace navigation, stable conversation panel and responsive layout.
- `ai-api.js`, `ai-stream.js`: conversation rendering, SSE parsing, cancellation and scroll preservation.
- `scheduling.js`, `review-drafts.js`: impact review, draft recovery and manager confirmation.
- `dashboard.js`, `briefing.js`: concise summaries and full report evidence.

Browser regressions are under `tests/e2e`. The older `README_ZH.md` is retained as a historical reference.
