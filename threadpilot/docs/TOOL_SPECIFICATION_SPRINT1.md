# ThreadPilot tool specification

Version: 1.1 · Updated: 2026-10-24 (Sprint 2 additions in section 10) ·

## 1. Architecture and authority

A bounded model planner translates requests into existing workflows. Deterministic tools retrieve current database facts, calculate risk and capacity, and prepare actions. The model explains returned facts in English; it does not calculate authoritative queue results or grant permission to execute a write. General questions may bypass business tools, but must not be presented as database-backed conclusions.

The primary data tables are `orders`, `production_log` and `workshops`. Snapshot freshness depends on upstream imports and updates. Production logs measure stage output, not order-level events or unique finished garments. The database is MySQ database; CSV files are seed inputs.

Tool calls carry `name`, `arguments`, `result`, `idempotent`, `requires_confirmation` and `executed`. Evidence can include source, record identifier, version, timestamp, original source and a URL.

## 2. Retrieval, judgement and tracing tools

| Tool | Inputs | Outputs / purpose | Limits and failures |
|---|---|---|---|
| `search_orders` | Validated order IDs or customer/product/stage filters | Matching records and evidence; locate the intended order | Multiple matches require selection; no invented ID or automatic choice for a write |
| `refresh_order` | One order ID | Current record and evidence | Missing/deleted orders fail; prior chat text is not fresh data |
| `summarize_orders` | Supported filters and summary/risk-overview intent | Counts and aggregates by stage/status/customer; risk overview uses shared queue results | Not arbitrary SQL or sales revenue; missing monetary fields cannot be inferred |
| `compare_orders` | Selected IDs and supported fields | Refreshed side-by-side records | No implicit business weighting or automatic scheduling |
| `rank_comparison` | Selected records, due-date or activity-date criterion | Explicitly ordered active IDs | Explain the selected criterion; completed work is not an active chase target |
| `assess_order_risk` | Refreshed ID and business date | Shared queue risk level, forecast, overdue status, reasons and activity observation | Risk is not probability; an activity gap does not prove a stoppage; completed lateness is separate |
| `assess_expedite` | One active order ID and current snapshot | Target lateness reduction, others' added lateness, net benefit and affected/newly late orders | No money/customer-weighted scoring; forecast uses shared capacity and calendar, not hidden model arithmetic |
| `prioritize_orders` | Window days, optional customer, business clock | Active orders due within the window, including overdue orders; due date/activity/ID ordering | Does not scan all far-future idle orders; each returned risk uses shared queue analysis |
| `check_normality` | Stage, target date, optional observed output | Comparison with up to eight prior same-weekday records; mean/min/max and evidence | At least three historical samples required; Sunday or missing observation is insufficient; below range is not a failure diagnosis |
| `explain_deviation` | Stage and date | Refreshed current and baseline production evidence, gaps and checks to perform | No recorded downtime/personnel/root-cause data means no causal diagnosis |
| `estimate_capacity` | Product, quantity, due date, delivery point, optional shipping buffer/packing loss | Conservative new-order capacity estimate, stage backlog and workshop options | Separate from queue simulation; no capacity reservation or delivery commitment; missing required fields prompt clarification |
| Evidence APIs (service) | Dataset and stable record ID; legacy CSV path uses row | Supporting current record and source metadata | Reject invalid datasets/missing records; compare saved answer version with current record |

## 3. Action and draft tools

| Tool / service | Inputs | Output / effect | Confirmation and failure boundary |
|---|---|---|---|
| `draft_chase` | Unique order, recipient, optional exact text/tone/reply deadline | Unsent editable chase-up draft | Missing recipient or precise deadline prompts clarification; a draft is not delivery |
| `send_chase` | Confirmed preview ID and final order/recipient/text | Gateway receipt with sent, not_sent or unknown status | Explicit confirmation, freshness and idempotency required; no gateway means not_sent; timeout is not proof of non-delivery |
| `save_internal_note` | Confirmed order and exact text | Internal action/audit record | Does not overwrite the order or send externally; stale preview rejected |
| `upsert_reminder` | Confirmed order, no_reply/no_activity condition and deadline | Stored conditional reminder | Supported conditions only; vague/past deadlines clarified; same session/order/condition updates existing reminder |
| `evaluate_reminders` (service) | Due reminders, current records and trusted reply events | Deduplicated in-app notification or satisfied-condition result | No external notification delivery; unavailable source leaves check pending; date-only activity is not hour-level evidence |
| `record_reply` (integration) | Authenticated event ID, order and timezone-aware received time | Deduplicated reply event | Reject untrusted/future/unknown-order events; chat claims cannot substitute for trusted ingestion |
| `review_reason_draft` | Draft/order context and drafting/revision instruction | Persisted English candidate based on expedite analysis | No schedule change; manual edits protected; version conflicts require reload; numeric facts are appended by the service |
| Scheduling review (service) | Review ID, save/apply/reject, reviewer, reason, optional draft/version | Saved recommendation, dispatch-priority update or rejection | Manager confirmation header and valid preview required; 15-minute expiry and snapshot/version checks; no separate manager token |

Draft generation, form adoption and final submission are distinct steps. Browser recovery is scoped to the backend and draft. The server persists draft versions and rejects stale updates. An AI-generated reason never counts as manager approval. Applying a review updates ThreadPilot's dispatch order only, not an external factory system.

Action previews bind the reviewed parameters and expire after 15 minutes. Confirmation is parsed on the server rather than delegated to model confidence. A new non-confirmation turn invalidates the pending preview. Repeated confirmations retain their idempotency identity. Do not blindly resend an unknown external delivery with a new key.

## 4. Discovery and model services

| Service | Input and result | Limits |
|---|---|---|
| `generate_morning_briefing` / MorningService | Current fact packet, business date and model; produces archived production review, priority bullets and action bullets with evidence | Real model generation plus grounding check; failure is explicit, no simulated AI report; cached by version/date/snapshot |
| Dashboard analysis | Current snapshot, validated prediction assets if available; counts, health and bounded advice | Legacy prediction probabilities are distinct from shared queue risk levels; stale predictions are not current evidence |
| Scheduled morning trigger | Authorized scheduler call after 07:00 Asia/Shanghai | Requires persistent background scheduling or an external timer; business clock and wall clock are distinct |
| General answer / narration | Recent conversation and tool results | English concise explanation; no web browsing and no implicit database access without tools |

The briefing page and dashboard summarize the same saved AI report. Dashboard text uses short bullet lists. Report evidence and calculation context remain accessible separately. Historical briefing email drafts are local drafts, not sent messages.

## 5. Auxiliary SQL tools

The separate SQL assistant uses `sql_db_list_tables`, `sql_db_schema`, `sql_db_query_checker` and `sql_db_query`. Inputs are table selections or SQL; query outputs include executed SQL, columns, rows, truncation information and query time. The checker is advisory: execution still passes AST/table/function restrictions, row/time limits and read-only credentials. Use a separate SELECT-only database account for the business tables. Defaults are 100 rows and 5 seconds. A query error is not evidence for a factual answer. Correct SQL syntax does not guarantee a correct business aggregation.

Data administration/imports, prediction imports and dashboard task updates are supporting APIs, not unrestricted chat tools. Shared application access control is not per-user authorization or tenant isolation.

## 6. Calculation and evidence rules

- Queue risk and expedite use the same current snapshot, Monday–Saturday calendar, historical same-weekday capacity, active quantities and dispatch priority. The simulation horizon is 200 working days. Missing order-level WIP requires conservative full remaining-stage quantities; future arrivals are excluded.
- Expedite benefit/cost is measured in order-working-days. Financial returns, client importance and penalties are intentionally excluded.
- New-order feasibility uses prior non-Sunday stage output averages and serial stage backlog estimates. Customer delivery uses an explicit buffer where required; this is a separate estimate, not a production commitment.
- Normality uses preceding same-weekday samples and compares with their observed range. A single low day cannot establish a sustained trend or a machine failure.
- Workshop defect-batch probability is not a defective-piece rate. A listed workshop may not fit the requested batch; eligibility needs checking.
- Evidence records preserve the answer's calculation context; a current-record link can change later. SQL aggregates are not full source-row provenance.

## 7. Conversation and stream behavior

Planning supports up to six tasks with bounded expansion of per-order reads. Session memory contains the last 16 messages and one latest snapshot per intent. Topics can switch and resume, but this is not unlimited memory. Multiple writes need separate reviewed previews. See [conversation architecture](CONVERSATION_UPGRADE.md).

Narration streams upstream text deltas after tools run. Exact action messages and basic fallbacks may be delivered in one chunk. Events are start, delta, done or error with 15-second keep-alive comments. Clients must not treat HTTP 200 as completed success. Cancellation does not roll back an already completed write. See the [SSE contract](../backend/STREAMING_API.md).

## 8. Acceptance and remaining integration work

Regression tests cover deterministic calculations, missing/ambiguous context, confirmations, version conflicts, persisted state, SSE and frontend recovery. See the dated [release validation](RELEASE_VALIDATION.md) for executed checks. These tests are not a model-accuracy benchmark or proof of real external delivery.

Before production release, validate MySQL migrations and grants, restart/multi-instance persistence, the public gateway's incremental SSE delivery, scheduler triggers, database backups and the actual chase/reply gateway. The current shared workspace has no individual user/tenant permission model.

For model evaluation, keep a separate reviewed question set covering retrieval, judgement, tracing, discovery, actions and ambiguous/unanswerable prompts. Store dataset/version, business clock, expected evidence, actual tool calls and actual side effects. Report failures and retries separately; do not claim an old test run validates this release.

## 9. Implementation map

| Concern | Source |
|---|---|
| Planner and narration | `backend/app/conversation.py` |
| State and confirmed actions | `backend/app/workflow_engine.py`, `workflow_store.py`, `sql_workflow_store.py` |
| Tool contracts | `backend/app/schemas.py`, `workflow_tools.py` |
| Current data | `backend/app/services/snapshot_service.py` |
| Shared queue and review | `backend/app/services/scheduling_service.py`, `backend/app/api/scheduling_api.py` |
| Review reasons | `backend/app/services/review_chat.py`, `review_drafts.py` |
| Morning generation | `backend/app/services/morning_service.py`, `backend/app/api/morning_api.py` |
| SQL guard | `backend/app/services/ai_sql_service.py` |
| Streaming | `backend/app/workflow_api.py`, `frontend/ai-stream.js` |

Request schemas are available from the running `/docs` and `/openapi.json` endpoints. Dependencies are pinned in `backend/uv.lock` and exported requirements.


## Chase drafting modes

`execution.chase` supports a summary draft (`chase_mode=summary`) and separate
order drafts (`chase_mode=separate`). Multiple explicit orders without a requested
mode produce a clarification listing only the current candidates. Morning briefing
chase-up defaults to a summary addressed to Me. `CHASE_SELF_RECIPIENT` can map Me to
a delivery address; when blank, the app asks for an address before a send preview.
A single-order draft asks for a recipient, not a tone. Separate drafts may be
prepared before their recipients are set; each recipient must be set before preview.

Drafts persist in the session JSON (`chase_context`, `chase_drafts`), requiring no
new tables. `Send draft 2 to manager@example.com` previews only that draft. The
existing expiring confirmation gate, source-record recheck and idempotency key
apply independently to each send. No bulk confirmation is accepted. Revision or
another request revokes an old preview. A sender webhook is still required for
actual delivery; a generated draft is never a delivery receipt. Summary webhook
payloads include `order_ids` as the full scope and `order_id` as the first order
(or an empty string for an operational summary without orders).

Model draft text is streamed as upstream deltas arrive, then saved only after a
complete response. Interrupted generations leave the previously saved drafts
intact. Deterministic clarification and confirmation messages are short single
chunks. `source_details` and `evidence` are rendered in a collapsed Source details
panel instead of appended to the answer body.

## 10. Sprint 2 additions (24 Oct 2026)

Driven by the first live evaluation (`evaluation/FAILURE_ANALYSIS.md`): 18 of 47 questions failed, none on arithmetic, all on routing, slot filling, coverage or missing refusals.

| Tool | Kind | Inputs | Outputs / purpose | Deliberately does not | Failure mode |
|---|---|---|---|---|---|
| `get_production_output` | Retrieval | stage (optional), date (ISO, yesterday/today, weekday name) | Recorded pieces per stage on that date from `production_log` | Compare or judge; that is `check_normality` | No record (Sunday or outside the log): says so, no number |
| `rank_active_orders` | Retrieval | criterion `idle_days` or `due_date`, optional customer, list length | Active orders ordered by one explicit rule with the rule stated | Score, weight or predict; an idle gap is not a stoppage | Unknown criterion falls back to idle days and says so |
| `list_workshops` | Retrieval | product/category, optional batch quantity | Eligible outside workshops (active, category match, batch cap) with queue, pickup, defect-batch probability and cost; excluded ones with the reason | Pick a workshop, reserve capacity, estimate the whole lead time | Category not inferable: lists all active with the rule |
| `predict_order_delay` | Judgement | one in-progress order ID | AFT delay probability + level, expected completion date, 80% range, model weights and validation (`docs/PREDICTION_MODEL.md`) | Use the current stage or customer; forecast completed orders | Unknown or complete order: not found / "applies to orders in progress" |
| `estimate_capacity` (v2) | Judgement | as before | Headline verdict from the shared queue simulation with the new order inserted (best case: no arrivals; expected: recent arrival rate), AFT on-time chance for the size, and the serial-backlog sum kept as a labelled worst case | Promise a date or reserve capacity | Queue needs a positive capacity baseline per stage; otherwise the worst case alone, labelled |
| `explain_no_data` | Refusal | the request | States the non-goal in plain words (no prices/revenue, no workers, no causes, no delete/cancel, no customer contact) and what the system can do instead | Ask "which order?" for a question no order can answer | Keyword guard only on unknown/low-confidence intents; a planner-classified `general.unanswerable` carries the reason |

Behaviour changes without a new tool: `check_normality` asks only for a missing stage and defaults the baseline to the previous eight same weekdays, stating the default; an unknown order ID is an answer ("There is no order ORD-999"), not an HTTP error; after a candidate list the server narrows on the product, quantity or due-date words in the next message itself; `summarize_orders` now carries overdue, due-today, idle-days and completed on-time aggregates so the narrator never improvises them; `resolve_date` understands weekday names; the planner no longer skips the attention-window question.

Regression: `backend/tests/test_sprint2_fixes.py` (annotated classifications) and `evaluation/run_annotated_eval.py` (47 questions, offline). Accuracy claims come only from `evaluation/REPORT_live_<date>.md`.
