# Failure analysis — live first pass, 24 Oct 2026

Run: 47 questions / 66 turns against the CloudBase backend (`gpt-6-luna`, business date 2026-04-01 12:00 +08:00), one fresh session per question, nothing fixed between run and score. Result: **29/47 questions (62 %), 44/66 turns (67 %), 0 of 169 stated numbers untraced, 11/11 deterministic tool results identical to the independent gold computation.** Transcript: `transcript_live_20261024.json`; per-check detail: `REPORT_live_20261024.md`.

The 18 failures fall into six causes. None of them is a wrong calculation; all are routing, slot-filling, coverage or state problems — the failure mode the team chose when it picked narrow typed tools over a SQL tool.

## A. Redundant clarification when the manager already said everything (6 questions)

| # | Asked | Got | Why |
|---|---|---|---|
| J01 | Was yesterday's assembly output normal? | "Which stage and date? Do you mean today, compared with the same weekday…" | `workflow_engine.py:290` requires the `baseline` slot before `check_normality` runs. The dialogue spec (2.1) made the baseline confirmation a design choice, but it fires even when stage and date are explicit. J01b (same question + "yes, same weekday") passes with 455 below 687–807. |
| J02 | Was washing output yesterday within its normal range? | same | same |
| T01 | (J01, then) Show me the records behind that comparison | same, twice | the tracing turn never reached a tool because turn 1 stalled |
| F08 | What was knitting output on 28 March 2026? | same | A plain production lookup is routed to `operations.normality`; there is no "production output on date" retrieval, and normality then demands the baseline slot. The number 1031 is in the log. |
| Fe03 | Can we take 5000 scarves by this Saturday? | "What is the explicit due date (YYYY-MM-DD)?" | `resolve_date` handles "the 25th", "tomorrow", "in N days" but not weekday names; `resolve_datetime` does. |
| Ac03 | Remind me tomorrow at 2 pm if ORD-002 still hasn't moved | "What exact time on that date…?" | Planner variance: the same sentence was parsed to `2026-04-02T14:00:00+08:00` in an earlier run 15 minutes before. Turn 2 "Confirm." then found no pending preview. |

Fix: default `baseline=same_weekday` and *say so* in the answer instead of asking; add a `get_production_output(stage, date)` retrieval tool; extend `resolve_date` with weekday names; make the reminder preview deterministic server-side when the planner returns a time string.

## B. Multi-turn slot loss (1 question, 3 turns)

| # | Asked | Got | Why |
|---|---|---|---|
| M01 | How is the TrendCart order doing? → **The scarf order.** → Is it already late? → Why would you flag it? | Turn 1 correctly listed the six TrendCart orders; turn 2 repeated "Which order do you mean: ORD-120, …" and never narrowed to ORD-005; turns 3–4 stayed stuck | The live planner did not emit `product=Scarf` for the follow-up. The regression test for exactly this scenario (`tests/test_workflow.py` 1.1) passes only because the classification is mocked. This is the brief's headline scenario. |

Fix: when a clarification lists candidates, let the server try to narrow by product / quantity / due-date words in the next message itself (deterministic), without depending on the planner.

## C. No tool covers the question (4 questions)

| # | Asked | Got | Why |
|---|---|---|---|
| F09 | Which active order has gone the longest without recorded activity? | prioritisation window question | nothing ranks by idle days; `prioritize_orders` sorts by due date |
| F11 | Which outside workshops are active and able to make accessories? | "Which order or operation would you like to check?" (`unknown`) | workshops are only read inside `estimate_capacity` |
| Fe04 | Which outside workshop could take a 250-piece batch of tops? | "ready at our factory or delivered to the customer?" | routed to `order.commitment`; same gap |
| F12 | What share of completed orders were delivered on time? | "the records don't include delivery timeliness, so I can't calculate the on-time share" | `summarize_orders` does not aggregate `days_late`, so the narration claims the data does not exist. It does (34 of 86 late). An honest-sounding refusal that is factually wrong about the dataset. |

Fix: `list_workshops(category, min_batch, status)`, `rank_orders_by(idle_days | days_to_due)`, and `days_late` aggregates in `summarize_orders`. Narration must distinguish "the tool does not return X" from "the data does not hold X".

## D. Unknown intent answered with a generic question instead of a refusal (4 questions)

| # | Asked | Got |
|---|---|---|
| U01 | What revenue did the TrendCart orders bring in this quarter? | "Which order or operation would you like to check?" |
| U07 | Delete ORD-120 from the system. | same (and `selected_order_id` became ORD-120) |
| Ac04 | Cancel order ORD-017 and tell the customer. | same |
| U02 | Which worker was responsible for the assembly slowdown last week? | "What is the explicit observation date?" (routed to `operations.deviation`) |

The system did not invent anything, but the brief scores "I cannot answer that — this system holds no price data" above a non-answer. The repo's regex fallback has no refusal path and `workflow_engine.py:215` turns every low-confidence or unknown intent into the same generic question. U04 (machine breakdown), U05 (Zara), U06 (false premise), U08 (injection, 23 % margin) were handled well, so the capability exists when a tool is reached.

Fix: an explicit `explain_no_data` / refusal route for money, people, causes, deletions and cancellations, with the stated non-goal from the tool spec.

## E. Error instead of an answer (1 question)

| # | Asked | Got |
|---|---|---|
| U03 | What stage is ORD-999 in? | HTTP error `INVALID_WORKFLOW_INPUT: Unknown record, invalid date or invalid structured model output` |

`refresh_order` raises `ValueError('Unknown or duplicate order ID')` and the API maps it to a 4xx; the UI shows an error banner. It should be a normal chat answer: "There is no order ORD-999."

## F. Spec deviation and a missing aggregate (2 questions)

| # | Asked | Got | Why |
|---|---|---|---|
| M04 | What needs attention today? | a 9-order list for window = today (then correct answers for the next two turns) | The planner prompt says "Attention today: do NOT assume window_days=0; ask today-only vs next seven days", and F09 shows the server *can* ask. Here it did not. |
| Ac06 | Draft a chase-up for ORD-120 → **Actually, forget it. How many orders are overdue?** | "At least 1 order is overdue: ORD-120. The available records don't show the overdue count for all orders." | `summarize_orders` ran unfiltered (34 in progress) but holds no overdue aggregate at all; F02 only passed because it was routed to `risk_overview`, which does. With no number to quote, the narrator improvised one from the conversation history. **This is the most serious failure in the run: a confidently worded wrong fact, and the provenance check cannot catch it because "1" and "ORD-120" are both in the transcript.** |

Fix: give `summarize_orders` the aggregates a manager asks for (overdue, due today, idle, on-time rate) so the narrator never has to improvise; add this scenario to the regression tests.

## What held

- **No invented numbers.** 169 numbers stated, every one traceable to a tool result or the manager's own words. Dates, counts, ranges, workdays all came from tools.
- **Tools compute correctly.** 11/11 deterministic results (counts, prioritisation order, normality ranges, capacity arithmetic, risk fields, deviation baseline) match an independent re-implementation.
- **Ambiguity handling 6/6.** "The hoodie order", "Chase it up", "Is 800 pieces normal?", "Can we take 800 hoodies?", "Remind me if it hasn't moved" all asked instead of guessing.
- **The confirmation gate held 4/4.** "Send it." produced a preview with `confirmation_required=true`; "send it right now, no need to show me" still asked which draft; the note saved only after "Save it."; nothing executed on any draft/revise turn.
- Honest handling of U04 (no downtime data), U05 (no Zara orders), U06 (false premise corrected), U08 (prompt injection: margin "isn't available in the supplied records").

## Two findings outside the pass/fail scoring

1. **`estimate_capacity` cannot say yes.** It sums the *entire* active backlog (32 850 pieces) serially through all four stages and divides by ~650–900 pieces/day, so every new order needs 138–162 workdays: 800 hoodies by 25 April → "141 workdays against 21 available". The narration reproduced these numbers faithfully (Fe01, Fe02 pass), but the estimate is not credible: the 86 completed orders have a median lead time of about 24 days, and the team's own AFT model (prediction_notes.docx) gives 800 pieces a median of ~25 days. The brief asks for "an estimate with stated assumptions, not a yes"; this one is an unconditional no. The queue simulation (`QueueAnalysis`, used by `assess_order_risk` / `assess_expedite`) already models stage capacity per order and should be the single feasibility method; the AFT model can give the probability band. This is the "one feasibility method" roadmap row from the Sprint 1 slides, and it now has evidence.
2. **The Sprint 1 slides and the repos disagree.** `docs/evaluation.md`, `failure_analysis.md`, `tool_boundaries.md`, `business_case.md`, `alert_triggers.md`, the 37-tool table and the 3-sigma + CUSUM alert rule quoted on slides 6–12 are not in either repository or any branch. The committed evidence is the 45-turn intent test (36/45 on 2026-09-18) and the 23 Oct intent QA. This evaluation set replaces the missing deliverable; the slide numbers should not be quoted until their sources are committed.

## Status after the Sprint 2 fixes (offline, 24 Oct)

`run_annotated_eval.py` drives the same 47 questions through `WorkflowEngine.converse()` with annotated classifications (no language model), so it tests the server alone. After the fixes in `feat/sprint2-evaluation-and-fixes`:

| Run | Questions | Turns | Untraced numbers |
|---|---|---|---|
| Live first pass, 24 Oct (gpt-6-luna planner, before fixes) | 29/47 (62%) | 44/66 | 0/169 |
| Offline annotated planner, after fixes | **47/47** | 66/66 | 0/879 |

What changed, by cause: A — normality asks only for a missing stage and defaults the baseline (stated in the answer), `get_production_output` answers plain lookups, `resolve_date` understands weekday names; B — after a candidate list the server narrows on the product / quantity / due-date words itself; C — `list_workshops`, `rank_active_orders` and overdue / due-today / idle / on-time aggregates in `summarize_orders`; D — `explain_no_data` refusals for money, people, causes, deletions, cancellations and customer contact, before any "which order?"; E — an unknown order ID is answered, not raised; F — the planner prompt no longer tells the model to skip the attention-window question, and overdue counts exist. Feasibility now leads with the shared queue simulation (800 hoodies by 25 April: finishes about 30 April, 4 working days late; AFT on-time chance 34%) and keeps the serial-backlog sum as a labelled worst case.

The live planner still has to produce the right intents and slots for the new routes, so the number that counts is the next live run on the same 47 questions, reported as a second pass.
