# Queue risk and manager-reviewed dispatch

This integration selectively adapts the queue engine from PR #4 (`b0cc93e`); it does not merge the unrelated simulation UI, Outlook integration or cloud deployment changes.

## What changes

The risk page, live chat, dashboard and new expedite review use one shared service and a current database snapshot. Risk and expedite compare **current orders only**, using the same capacity and approved priority queue. This intentionally replaces the PR's mixed future-arrivals comparison. Logistic-regression exports remain available as a separate historical prediction module and are not the operational risk source.

The flow is: risk → analyze expedite impact → review target benefit and every affected order → manager decision → save advice, reject, or apply a dispatch priority. Chase-up drafts, notes and conditional reminders continue through the existing chat preview/confirmation workflow. An analysis or chat confirmation cannot modify the dispatch queue.

## Deploy

From `backend/`, install the existing locked dependencies and run `python -m alembic upgrade head` with the intended database configuration. The new revision `0006_dispatch` follows this branch's `0005`; it creates `dispatch_schedule` and `dispatch_reviews`. It is distinct from the unrelated PR's email-delivery revision. No live database migration is performed just by importing the application.

The frontend now defaults to its own host (including LAN/mobile access); set `window.THREADPILOT_CONFIG.apiBase` explicitly before `config.js` for a separate backend. It no longer silently routes non-localhost visitors to a fixed cloud service.

The front end needs access to `/api/scheduling/*`. Existing `API_ACCESS_TOKEN` protects workspace access when configured. Manager decisions additionally require `DATA_API_TOKEN` and `X-Confirm-Write: true`. The UI requests this credential for each review and never saves it to browser storage. The reviewer name is a declared audit label; this application still uses a shared management credential, not individual identity/role accounts.

## Calculation

- Monday–Saturday, one stage transition per order per day, earliest due date then order ID unless manager priorities exist.
- Capacity uses up to eight prior same-weekday output records before the previous working day, with at least three observations per stage. The previous-60-day completed pieces/working day to average logged packing ratio scales all stages, clamped to 1–3 (requires at least ten completed orders). This is a planning assumption, not measured extra workshop capacity.
- Current-stage partial work is unavailable, so the full order quantity remains at that stage and subsequent stages. The engine's per-order daily allocation limit is max(20 pieces, 60% of stage capacity), still bounded by total stage capacity.
- Overdue is a fact. For other active orders: projected lateness ≥5 working days is high, 1–4 is medium, otherwise low. Suspicious inactivity (five idle working days while later-due work at the same stage has moved recently) raises risk and blocks application pending investigation. This is a suspicion, not proof of a stopped machine/order.
- Benefit is target lateness reduced. Cost is other current orders' signed change in lateness. Net is benefit minus cost, in equally weighted order-working-days. No money, customer priority or penalty weights.
- Recommend expedite when benefit and net are both at least two days; newly late orders require an explicit trade-off. A manager can override a low-net recommendation with a reason, provided it actually advances the target and the result is computable. Suspected stalled orders, absent capacity and unbounded projections cannot be applied.
- Projections beyond 200 working days are unavailable; they are never reported as a fabricated finite benefit. Confidence labels reflect distance from the threshold, not calibrated probability.

## Applying a decision

Applying moves the target before all existing priority orders at each remaining stage. It stays prioritized until completion or until another approved order is put ahead. This is a persistent **application dispatch plan**, not a connection to machinery, an ERP or an external MES. It does not change quantities, due dates or recorded production stages.

Preview payloads include their input fingerprint, capacity, assumptions and impact list. Decisions expire after 15 minutes and are rejected if any business input, business date, algorithm version or queue version changed. Preview/apply operations share the existing database write lock with imports and CRUD. Schedule updates and audit records commit together. Retrying the same decision returns the original result without applying twice; changing an already-final decision requires a new preview.

Saved/rejected/applied decisions are visible in Risk → Decision history. The most recent 100 are shown; original payloads remain in the database. Analysis previews never count as reviewed decisions.

## Acceptance

1. Migrate an empty database and an existing 0005 database; confirm old business rows survive.
2. On the same business date, confirm dashboard, risk page and chat report identical risk for an order.
3. Analyze an order and compare its finish dates, lateness benefit, affected orders and net benefit by hand.
4. Save/reject without altering the queue. Approve with management credentials and verify the next projection reflects the new queue, including after restarting.
5. Update an order or approve another queue adjustment between preview and decision: the old preview must return conflict.
6. Retry an approved decision: queue version must not increment twice.
7. Test missing capacity, a suspected stalled order, newly late orders, a negative-net proposal and the 200-day horizon.
8. Ask “Should we expedite ORD-005?” then “它会影响谁？”. The target remains ORD-005. Ask to draft a chase, save a note or set a reminder; existing confirmation rules still apply.

No real email is sent and no production database is modified by unit tests. MySQL and browser integration need the target deployment's configuration; mocked model classification verifies routing, not real-model intent accuracy.

### Integration validation

- Backend regression: 104 passed, 1 skipped (MySQL integration requires `TEST_MYSQL_URL`). This includes migration from an empty database and revision 0005, stale decisions, concurrent approvals, idempotency and shared risk/chat calculations.
- Isolated SQLite backend and real browser: analysis, manager approval, persisted priority, recalculated finish dates, decision history and desktop/mobile layouts passed (`tests/e2e/verify_scheduling.cjs`).
- Existing chat streaming/cancellation/retry and dashboard task persistence/failed-save rollback browser checks passed. Live-model classification and a production MySQL deployment still need environment-specific acceptance.
