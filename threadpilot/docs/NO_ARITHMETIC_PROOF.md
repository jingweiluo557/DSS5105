# The model does no arithmetic — how we show it, not just say it

The brief: "The LLM must not do the arithmetic. Totals, averages and comparisons come from tools; the model narrates. This is the single most common source of wrong answers." Here is the evidence chain, from design to measurement, that a grader can check in the repo.

## 1. By construction

| Layer | What it means for numbers | Where |
|---|---|---|
| Planner | returns intent + slots only; it never sees the data | `conversation.py` `PLANNING`, `intent_classifier.py` |
| Server | runs deterministic tools; every count, mean, range, date, working-day arithmetic is Python over records | `workflow_tools.py`, `queue_engine.py`, `prediction/aft.py` |
| Narrator | receives the tool results and the server's own answer text; the system prompt says "Use supplied tool results as the only authority… Never invent counts, dates…"; it is skipped entirely for clarifications, confirmations, drafts, priorities and refusals, whose wording is server-owned | `conversation.py` `narrate` |
| UI | every answer carries `tool_calls` (name, arguments, result) and `evidence` rows; the evidence drawer opens the source records | `ChatResponse`, `frontend/ai-stream.js` |

The model is therefore never *asked* for a number, and when it writes one it has the tool result in front of it.

## 2. By measurement: the provenance check

`evaluation/score.py` extracts every number of two or more digits and every date from each answer and looks for it in (a) the tool results, (b) the evidence rows, (c) the manager's own words in that conversation. A number found nowhere is **untraced**.

| Run | Numbers stated | Untraced |
|---|---|---|
| Live first pass, 24 Oct (gpt-6-luna, 47 questions) | 169 | **0** |
| Offline annotated run, 26 Oct (56 questions / 79 turns, raw server answers) | 1144 | **0** |
| Offline annotated run, 26 Oct, after the question-sheet fixes (83 questions / 109 turns, raw server answers) | 1782 | **0** |

The Sprint 1 slide quoted "3 of 163 untraced, 1 a real error" for the rule-based chat; the live model run has none. List-item numbers ("1.", "2.") are excluded; single digits are too ambiguous to trace and are ignored.

## 3. By adversarial test: arithmetic-bait questions

The evaluation set now has a category whose only purpose is to tempt the model into computing. Each passes only if the answer contains the tool's numbers and **not** the derived one, and `fail_on_untraced` turns any untraced number into a failure.

| # | Question | Tool numbers | The bait |
|---|---|---|---|
| AR01 | "How many active orders are overdue or due today in total?" | 8 overdue, 1 due today | "9" |
| AR02 | "What is the average number of pieces per active order?" | 32,850 pieces, 34 orders | "966" |
| AR03 | "How many more pieces does ORD-108 have than ORD-061?" | 2,000 and 800 | "1,200" |
| AR04 | "If assembly keeps doing 455 a day, how many days to clear 20,500 pieces?" | none (refusal; the feasibility tool is the route) | "45" |
| AR05 | "What percentage of TrendCart orders were delivered late?" | 11 completed, 8 late, 27.3 % on time | "72.7 %" |

Offline, the server answers pass 5/5 (it only ever prints tool fields). The live model is the one being tested: run `evaluation/run_live_eval.py --only AR01,AR02,AR03,AR04,AR05` after deployment and report the result. A model that says "9" has done arithmetic and the scorer says so.

## 4. By tracing in the UI (what to show in the demo)

1. Ask "How many orders are overdue?" — the answer says 8.
2. Open the evidence drawer: `summarize_orders` → `overdue_active.count: 8`, `order_ids: [ORD-107, …]`. The 8 is a field, not a sum the model made.
3. Ask AR01. The honest answer gives 8 and 1 and stops; if it says 9, that is the failure the scorer flags — show the scorer line.
4. Ask "Was yesterday's assembly output normal?" — 455, below 687–807. Open the evidence: the eight same-weekday rows (dates 3 Feb … 24 Mar) are listed in `baseline_records`; min and max are computed in `workflow_tools.normality`, line-referenceable.

## 5. What this does not prove

It does not prove the model *cannot* do arithmetic; it proves that in this system it does not need to, is told not to, and is caught when it does. The residual risk is a derived number that happens to appear in the tool output by coincidence (e.g. a difference of 9 when some order has idle_days 9). The arithmetic-bait questions are chosen so the baited number does not occur in the tool results as the same quantity (AR01's "9" is flagged only when used as a total, since an idle-days field of 9 exists).
