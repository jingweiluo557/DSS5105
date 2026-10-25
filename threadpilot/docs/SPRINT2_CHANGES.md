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
- Offline annotated-planner run after the fixes: 47/47 on the original questions; on the current 56-question set 56/56 scenarios, 79/79 turns, 0/1144 numbers untraced (`evaluation/REPORT_annotated.md`, re-run by CI on every push). The team's 45-turn workbook regression: 45/45 on the CSV path.
- Still to do: deploy, re-run the 56 questions live and report it as a second pass (the planner must now emit the new intents).

## Not changed
- Frontend. The Feasibility page still uses its own local estimate; a follow-up should call `estimate_capacity`.
- Database schema, migrations, cloud functions, email.

## 26 Oct additions (same branch)

- **Alert policy** (`services/alert_policy.py`, `alert_delivery.py`, `api/alerts_api.py`, `docs/ALERT_POLICY.md`): three tiers (P1 email now / P2 digest / P3 briefing), dedupe keys with cooldowns, escalation only when worse, no re-emailing of unresolved items, 3-a-day cap, quiet hours, shelving, usefulness KPIs. Dry run by default (`ALERT_EMAILS_ENABLED=false`); runs on the existing minute timer. On the seed data: 1 P1 email (assembly 3 days below range + two near-due misses), everything else in the digest; second tick 0 emails.
- **Feasibility capacity picture** (`api/feasibility_api.py`, `frontend/feasibility-chart.js`): the Feasibility result page now calls the same `estimate_capacity` tool as the chat and draws one stacked bar per stage (queued pieces + the new order) against the pieces the stage can complete before the due date, with the queue-projection finish date, the AFT on-time chance and the bottleneck stage. Scrolls horizontally on phones.
- **Evaluation set v2026-10-26**: 56 questions / 79 turns — adds 5 arithmetic-bait questions (`fail_on_untraced`), two multi-turn scenarios (correction; topic switch and resume) and two discovery questions. Offline 56/56 with 0 of 1,144 numbers untraced; the 24 Oct live first pass stays 29/47 on the questions it covered (the 9 new ones are marked "not in that run").
- `compare_orders` accepts pieces / product / customer fields.
- Docs: `TOOL_SPECIFICATION.md` (one table, 28 tools and services, with non-goals and failure modes), `VAGUE_QUESTIONS_AND_DIALOGUES.md`, `NO_ARITHMETIC_PROOF.md`.

## 26 Oct, second batch — closing the gaps (same branch)

- **CI**: `.github/workflows/threadpilot-backend.yml` runs the backend pytest suite and the offline evaluation replay (strict) on every push; failures appear as check-run annotations; `docs/openapi.json` is re-exported and committed automatically when routes change.
- **Discovery**: `find_anomalies` / intent `operations.discovery` — the brief's fourth tool kind as a chat tool, sharing detectors with the alert policy (questions D01, D02).
- **Stage watches**: "remind me tomorrow if packing is still behind" is now a reminder condition (`stage_below_range`), evaluated with `check_normality` in both reminder stores.
- **Roles**: optional `MANAGER_ACCESS_TOKEN`; with it set, the ordinary key cannot confirm writes, apply reviews, change email settings or mute alerts. `GET /api/v1/whoami`.
- **Voice**: `frontend/voice.js` — speech-to-text into the composer, "Read aloud" on answers (browser-native, no audio stored).
- **Dispatch notice** after an applied expedite review, drafted through the chat gate.
- **Feasibility page** headline is the shared estimate once loaded; the local model is labelled as the pre-check.
- **Briefing email** carries an alert-budget line.
- **Docs**: `BUSINESS_CASE.md` (reconstructed from the Sprint 1 deck, labelled estimates), `SPRINT1_EVIDENCE.md` (every slide claim mapped to a file or marked superseded).
- Evaluation v2026-10-26: 56 questions / 79 turns, offline 56/56.

## 26 Oct, third batch — the CEO home screen (branch `feat/ceo-home-screen`)

Driven by the ten-second test in `docs/CEO_INTERFACE_REVIEW.md`: no screen on the live build said what to decide today before showing counters and prose.

- **Home screen**: status line (date · RED/AMBER/GREEN · three facts) from the alert tiers; at most three "Decide today" cards with one button each (ask the floor / review options / confirm a new date / call the customer), from the same detectors as the alert emails; order health as one stacked bar with the 30-day on-time rate; production pulse as four bars against the previous-eight-same-weekday band; the briefing reduced to its first sentence per section and never regenerated on load; to-dos limited to the manager's items and AI next steps that name an order or a stage; the chat box on the page. No nested scroll regions. Backend: `services/home_service.py` + `GET /api/dashboard/home` (pure Python over the snapshot), `tests/test_home_screen.py`, `tests/e2e/dashboard_ai_render.cjs`.
- **Chat**: a `facts` SSE event sends the server's answer before the narration; answers render light markdown; ranking questions are answered as numbered lists; sources collapse to one line; order cards fold when more than two.
- **One risk vocabulary**: late / at risk / on track / unassessed everywhere; the AFT chance (`forecast` on each `/api/scheduling/risk` row) is one line inside the order card; the 100-point rule score is retired; the model export tab leaves the manager navigation (linked from Settings).
- **Expedite review**: verdict and consequence first, before/after finish bar, "already first in its queue" case named with the two options left; all labels English.
- **Fixes**: `#/` lands on the dashboard; Orders opens with late / at-risk lists and the full table behind a click; activity gaps coloured at 5 and 10 days; watches banner corrected; Settings leads with the briefing state and moves the demo clock under "Demo"; the briefing prompt asks for at most three decisions of at most 20 words naming an order or a stage.
