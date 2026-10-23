# Personal Outlook connection

This integration uses Microsoft Graph delegated `Mail.Send` and MSAL's authorization
code flow with PKCE, state and nonce validation. MSAL includes `openid`, `profile`
and `offline_access` automatically. It does not request mailbox-read permission.

## Setup

Register a personal-Microsoft-account application, with a **Web** redirect URI
`http://localhost:8000/api/outlook/callback`. Add delegated `Mail.Send`. Create a
client secret and save its **Value**, not its ID, in `backend/.env`:

```dotenv
OUTLOOK_CLIENT_ID=<application ID>
OUTLOOK_CLIENT_SECRET=<secret value>
OUTLOOK_REDIRECT_URI=http://localhost:8000/api/outlook/callback
OUTLOOK_AUTHORITY=https://login.microsoftonline.com/consumers
OUTLOOK_ENCRYPTION_KEY=<Fernet key>
```

Generate a Fernet key once with the command in `.env.example`. Keep this key stable
and backed up privately: changing it makes existing authorization and history
unreadable. Do not commit `.env` or `backend/runtime`.

Install the locked dependencies when no running Python process holds their files,
then restart the backend. Open **http://localhost:8000/outlook.html** (use localhost,
not 127.0.0.1, so the OAuth browser cookie returns to the same host). Enter the
existing `DATA_API_TOKEN` from `backend/.env`; if configured, also enter
`API_ACCESS_TOKEN`. Click **连接 Outlook** and sign in to the personal account that
has an actual Outlook.com mailbox. Azure's management account may be different.
Accept the Microsoft consent screen yourself. Authorization grants sending access;
it does not itself send any email.

After the redirect, enter the management token again and check the connection.
Fill in recipients, subject and body, preview, then explicitly confirm sending.
Existing morning-summary text can be copied into this first-version connection page;
the dashboard's saved-draft workflow remains separate.

## API

All endpoints except the callback require `Authorization: Bearer <DATA_API_TOKEN>`.
When enabled, the app middleware also requires `X-ThreadPilot-Token`.

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/outlook/status` | Config readiness and connected account |
| POST | `/api/outlook/connect` | Set a 10-minute HttpOnly browser cookie; return authorization_url |
| GET | `/api/outlook/callback` | Validate browser cookie/state/expiry, consume flow once, exchange code |
| POST | `/api/outlook/send` | Send reviewed content; requires `X-Confirm-Write: true` |
| GET | `/api/outlook/messages` | Last 50 submitted messages and statuses |
| POST | `/api/outlook/disconnect` | Clear local account/cache/pending flow; requires confirmation header |

Send body:

```json
{"id":"a-unique-UUID","to":["recipient@example.com"],"subject":"Subject","body":"Text","confirmed":true}
```

Persist and reuse the same UUID when retrying the same operation. Duplicate UUIDs
do not resubmit; reusing one with changed content returns 409. `accepted` means
Graph returned 202, not delivery confirmation. `rejected` means Graph rejected the
request. `unknown` means a timeout, network failure or server error; `submitting`
may remain after a process crash. Never automatically retry unknown/submitting
operations: inspect Outlook Sent Items first. A new ID is a new send.

## Storage and deployment

### Settings and automatic morning briefing

Open `/#/settings` directly. These endpoints use the existing workspace access
control (`API_ACCESS_TOKEN`), without a separate administration-key prompt. Outlook connection/reconnection,
manager recipient/name, subject prefix, daily schedule toggle and customer contacts
are managed here. Customer contacts are saved only; they do not receive the manager
briefing. Preferences use optimistic versions to reject overwriting newer edits.

Set `EMAIL_SCHEDULER_ENABLED=true` for a persistent application worker. It checks
every two seconds and begins generating the current business day's report at 07:00
Asia/Shanghai (UTC+08:00), using the shared business clock. Generation can take time before submission. Enabling
after 07:00 starts the following day. A delayed worker checks the current day only,
without sending a backlog of old days. The authenticated cloud endpoint
`POST /api/internal/briefings/run` also attempts delivery using the same daily claim;
use the existing `SCHEDULER_TOKEN` bearer authentication. Repeated triggers share
one daily claim when they share the same Outlook store.

Generation failures retry up to three attempts, five minutes apart. A stale generation
claim is recoverable after 15 minutes. Once submission begins, no automatic resend
occurs, including ambiguous outcomes. Inspect Sent Items for `unknown`/`submitting`.
The report must be dated today; its separate business date is included in the email.
Changing the recipient or pausing while generation runs cancels that day's job.

`GET/PUT /api/email/settings`, `GET /api/email/activity`, and
`POST /api/email/connect` or `/disconnect` use workspace access control. Writes
also require `X-Confirm-Write: true`. The standalone `/api/outlook` test endpoints
continue to require the administration key. Activity Log shows persisted daily
entries with expandable recipient, subject, report body and delivery diagnostics.
`accepted` records Graph acceptance, never confirmed receipt. The last 100 daily
entries are displayed. No sample success records are inserted.

The existing database must be migrated to `0008_ai_morning` for report generation.
For cloud rollout use a single persistent service with durable `OUTLOOK_STORE` and
the same encryption key, or replace this store with shared transactional storage
before enabling independent replicas/serverless execution. Deploying a timer alone
does not make a temporary SQLite store durable.

The single connected mailbox is shared by this installation's authenticated admin.
This is not a multi-user mailbox system. The default local SQLite file is
`backend/runtime/outlook.sqlite3`. Token caches, login flows and message payloads
are Fernet encrypted. SQLite transactions serialize local cache updates and message
claims. Keep the database on persistent local disk; do not enable this store on
ephemeral/serverless or multiple-host deployments without replacing the storage.

The callback is exempt from the app's header token because Microsoft redirects
cannot set it. The one-time flow, browser cookie and state protect that endpoint.
Uvicorn callback query strings are redacted; configure any reverse proxy not to log
callback queries either. Use HTTPS when deploying beyond localhost.

Disconnect clears local credentials; it does not revoke consent at Microsoft.
Revoke that separately in your Microsoft account's app permissions when needed.

## Troubleshooting

- Missing configuration: save the correct `backend/.env`, then restart.
- Redirect mismatch: the registered Web URI and OUTLOOK_REDIRECT_URI must match.
- Failed callback: start from localhost, allow cookies, finish within ten minutes,
  check secret expiration/Value, and restart the connection after cancellation.
- Authorization renewal: reconnect; a revoked refresh token cannot be repaired silently.
- Graph rejects sending: verify that the signed-in personal account has an Outlook
  mailbox and has granted Mail.Send. A QQ-address Microsoft login alone does not
  establish that an Outlook mailbox exists.
- Tests use fake Microsoft responses and temporary databases; they send no mail.

References: [MSAL Python](https://learn.microsoft.com/en-us/entra/msal/python/),
[Graph sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0).


## Running business clock for demonstrations

Settings → Business date & time → Start demo clock persists an offset from real
UTC time. The clock continues at 1× speed across refreshes and service restarts.
All business-date calculations, workflow reminders, morning generation, dashboard
and dispatch/review times use this clock. Authentication expiry and transport
metadata continue to use real time. `BUSINESS_CLOCK_STORE` defaults to
`backend/runtime/business-clock.sqlite3` and must be durable with the email store.
Until a clock is saved, the legacy BUSINESS_NOW value remains supported.

Each demo reset has a unique run ID. A morning briefing is claimed once per business
day per demo run, retaining previous runs' logs. Setting 2026-04-01 06:59 triggers
preparation at 07:00 one real minute later; AI generation and inbox delivery take
additional time. Setting a time at/after 07:00 starts the next morning, not an
immediate backfill. Switching back to real time restores normal daily de-duplication.
The Settings form explicitly states that configured recipients receive real emails.

For delayed customer emails, draft the message in AI workspace with an explicit
recipient address, then request `Send draft 1 in 2 minutes`. The app shows recipient,
body and business send time and requires confirmation. It queues the confirmed
message in durable encrypted storage and shows `Scheduled` in Activity Log.
At the due business time the worker submits once to Graph, recording acceptance
or failure. Clock resets cancel previous runs' pending scheduled emails; already
submitting emails cannot be recalled. No ambiguous submission is auto-retried.
The feature does not infer a customer's recipient address from their name.

Clock APIs: GET/PUT `/api/email/clock`, existing workspace access, confirmed-write
header for PUT, optimistic version, `mode` demo/live and timezone-aware `target`.
Active tabs resync with the server and reload when the business date/run changes.

## Reviewed department chase-up emails

Settings now stores department recipients for KNITTING, ASSEMBLY, WASHING and
PACKING. Blank addresses are allowed; an unconfigured department blocks the send
preview until the manager supplies an address. Existing settings default to an
empty department map.

Open an order's chase-up action or ask AI to draft a chase-up for an order ID.
The draft uses the order records and maps its current stage to a department.
Review draft opens a confirmation containing the department, recipient, subject
and exact body. Revisions require a new review. Only Confirm send submits the
reviewed content through the connected Outlook account. The server rechecks order
snapshots, confirmation age and business-clock run before submission.

Activity Log records order IDs, department, recipient, subject, body and provider
result for immediate and scheduled sends. Microsoft acceptance is not proof of
inbox delivery. Duplicate confirmations reuse the submission ID, and uncertain
submissions are not automatically retried. Department addresses must be supplied
by the manager; no default department recipient is invented.

## Context and time corrections (2026-10-24)
New chase requests follow the current order. Department changes regenerate recipient
selection and require a fresh preview. Multi-order follow-ups clarify the target.
Business dates and review windows are rendered distinctly. Relative send times and
reply deadlines become absolute timezone-aware business timestamps when supplied;
repeated review does not postpone them. A clock reset invalidates older drafts.
The server appends the absolute reply deadline to the reviewed email body.
Transport/audit timestamps and OAuth lifetimes retain real-clock semantics.
