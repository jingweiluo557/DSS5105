# Queue risk and expedite review

Risk and expedite analysis share `SchedulingService` / `QueueAnalysis` and the current database snapshot. The sequence is: identify risk, compare expedite impact, show the target gain and affected orders, obtain a manager decision, then save a recommendation or apply dispatch priority. Chase-ups, notes and reminders use separate confirmed action workflows.

## Calculation basis

The simulation uses Monday–Saturday working days, current active orders and historical same-weekday stage capacity adjusted by completed volume. It conservatively counts complete quantities in remaining stages because order-level remaining WIP is unavailable. The forecast horizon is 200 working days; unknown future orders are excluded. Approved dispatch priority influences subsequent simulations.

An expedite preview runs the original and changed queue against the same snapshot and capacity basis. It reports target lateness reduction, added lateness across other orders, the net difference and affected/newly late orders. These are order-working-days, not financial returns. Order amount, customer importance and penalty costs are excluded. Recorded overdue status is a fact; forecast risk levels are not probabilities or guaranteed delivery dates.

The legacy new-order capacity estimate remains a separate conservative feasibility tool; it is not the shared queue simulation. Idle-day dashboard indicators also describe activity gaps rather than the queue forecast.

## API and review lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/scheduling/risk` | Current shared queue-risk results |
| `POST /api/scheduling/orders/{order_id}/preview` | Persist a reviewable before/after impact preview |
| `POST /api/scheduling/reviews/{review_id}/decision` | Save, apply or reject a reviewed preview |
| `GET /api/scheduling/history` | Read prior decisions |
| `POST /api/scheduling/orders/{order_id}/draft` | Open a persisted reason draft |
| `GET /api/scheduling/drafts/{draft_id}` | Restore draft state |
| `PATCH /api/scheduling/drafts/{draft_id}` | Save edits with the expected version |
| `POST /api/scheduling/drafts/{draft_id}/{action}` | Generate, adopt or refresh a draft |

Decision requests contain `decision`, `reviewed_by` and `note`; a linked draft supplies both `draft_id` and `draft_version`. Final submission requires `X-Confirm-Write: true`. There is no separate manager token, although general application access control still applies when enabled. The reviewer name is an audit label, not authenticated identity.

The server checks preview expiry (15 minutes), snapshot/date/algorithm/queue freshness and draft versions. Stale previews need recalculation. Duplicate decisions are protected from repeated scheduling effects. Applying updates ThreadPilot dispatch priority only; it does not send a production instruction to an ERP.

## Review reasons

The model drafts English qualitative reasoning; the service appends verified numerical impact facts. Candidate text is separate from adopted form text. Manual edits are protected from silent replacement, versions prevent stale updates, and browser recovery is scoped to the backend and draft. Draft generation/adoption is not final approval. The manager reviews the complete form and explicitly confirms the final submission.
