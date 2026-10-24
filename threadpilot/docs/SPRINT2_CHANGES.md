# Sprint 2 changes (branch `feat/sprint2-evaluation-and-fixes`, 24 Oct 2026)

Why: the first live evaluation of the CloudBase deployment (47 questions, `evaluation/REPORT_live_20261024.md`) passed 29/47 with 0 invented numbers; every failure was routing, slot filling, coverage or a missing refusal. This branch adds the evaluation deliverable and fixes those causes.

## Added
- `evaluation/` — eval set builder (gold from CSVs), scorer, live/offline runners, 24 Oct transcript and report, failure analysis.
- `backend/app/prediction/aft.py` + `duration_model.json` — the teammate's log-normal AFT lead-time model, ported to pure Python (bit-exact against the scipy original on all 34 open orders); `scripts/train_aft_model.py` refits it.
- Tools: `get_production_output`, `rank_active_orders`, `list_workshops`, `predict_order_delay`, `explain_no_data` (intents `operations.output`, `order.rank`, `data.workshops`, `order.forecast`, `general.unanswerable`).
- `backend/tests/test_sprint2_fixes.py` — 15 regression tests on the server with annotated classifications.
- `docs/PREDICTION_MODEL.md`; section 10 of `docs/TOOL_SPECIFICATION_SPRINT1.md`.

## Changed
- `estimate_capacity`: headline verdict from the shared queue simulation with the new order inserted (best / expected case) plus the AFT on-time chance; the serial-backlog sum stays as a labelled worst case. 800 hoodies by 25 April: "unlikely — finishes about 30 April, 4 working days late; 34% on-time chance for this size" instead of "141 workdays against 21".
- `check_normality` / `explain_deviation`: ask only for a missing stage; baseline defaults to the previous eight same weekdays and the answer says so; `baseline_records` listed for tracing.
- `summarize_orders`: overdue, due-today, idle-days and completed on-time aggregates; a zero-match customer/product is named as such.
- Unknown order ID → a chat answer ("There is no order ORD-999"), not HTTP 4xx.
- After a candidate list, the server narrows on product / quantity / due-date words in the manager's reply (the "The scarf order." scenario) without depending on the planner.
- Refusals (money, people, causes, delete, cancel, customer contact) come before any "which order?" question.
- `order.risk` answers start with a plain status line (not past due / overdue by N days, idle days); reminder confirmations name the order and time.
- `resolve_date` understands weekday names ("this Saturday", "next Monday").
- `QueueAnalysis`, `ASSUMPTIONS`, `fingerprint` moved to `services/queue_engine.py` (pure Python; re-exported from `scheduling_service` so every importer is unchanged).
- Planner prompts (`intent_classifier.py`, `conversation.py`): the new intents; overdue/idle/on-time questions are `order.summary`; the attention-window question is asked, not skipped.

## Measured
- Live first pass before the fixes: 29/47 questions (62%), 44/66 turns, 0/169 untraced numbers, 11/11 tool results verified.
- Offline annotated-planner run after the fixes: 47/47, 66/66, 0/879 untraced. The team's 45-turn workbook regression: 45/45 on the CSV path.
- Still to do: deploy, re-run the 47 questions live and report it as a second pass (the planner must now emit the new intents).

## Not changed
- Frontend. The Feasibility page still uses its own local estimate; a follow-up should call `estimate_capacity`.
- Database schema, migrations, cloud functions, email.
