# 100 questions × 3 contexts (sheet "100Q 3 Context Same Structure")

The team's 100-question sheet, each question phrased three ways (formal, rephrased, shorthand/typos), run through the
workflow engine as one running conversation per scenario per context (the sheet is written that way: 1.2 "refresh an
active order" refers to the order established in 1.1).

| File | What it is |
|---|---|
| `questions.json` | The sheet: no, scenario, field, the three phrasings, the sheet's expected answer where given, PIC. |
| `similar_questions.json`, `annotations_similar.py`, `grade_similar.py` | The "Similar Questions" tab: the same 100-row structure with another factory's vocabulary (jackets, uniforms, embroidery / cutting / sewing / inspection, W9, Cedar Apparel, Seabrook Textiles, ORD-201–312, May–June 2026). Most rows name things ThreadPilot's records do not hold, so it tests grounding: say what is not on file (and what is), never invent, never act. Run with `Q100_SET=similar`. |
| `run_q100.py` | Offline run through `WorkflowEngine` with two planners: `ideal` (the intent and slots a careful reader would return per row, so it measures the server) and `fallback` (the keyword planner used when the model is down). Writes `answers_<mode>.json`. `Q100_SESSION=field` for the stricter one-session-per-field reading. |
| `run_live_q100.py` | The same questions over HTTP against a deployment (the real planner model). Token from `THREADPILOT_TOKEN` only. Writes `answers_live.json`. |
| `grade.py` | One rule per question (PASS / PARTIAL / FAIL) from the brief, the sheet's expected answers and the gold facts computed from the CSVs on 2026-04-01. Writes `*_graded.json` and prints totals by field. |
| `results/` | Graded runs before and after the 8 Nov 2026 fixes, ideal reading and keyword fallback. |

```bash
cd threadpilot/evaluation/q100
python run_q100.py ideal && python grade.py answers_ideal.json
python run_q100.py fallback && python grade.py answers_fallback.json
THREADPILOT_TOKEN=... python run_live_q100.py --base https://<backend> && python grade.py answers_live.json
Q100_SET=similar python run_q100.py ideal && python grade_similar.py answers_similar_ideal.json
```

## Result (ideal reading, n = 300; all runs graded with the same final grader)

| Run | PASS | PARTIAL | FAIL | Questions right in all 3 contexts |
|---|---|---|---|---|
| Before (code at PR #14) | 159 (53%) | 70 | 71 | 34 / 100 |
| After PR #16 (8 Nov, first round) | 246 (82%) | 53 | 1 | 71 / 100 |
| After the gap fixes (8 Nov, second round) | **300 (100%)** | 0 | 0 | **100 / 100** |
| Keyword fallback, before → after | 7 → 17 (2% → 6%) | 30 → 29 | 263 → 254 | 0 → 3 |

PASS includes the clarifications the team's dialogue design prescribes (which order of a customer, factory vs delivered,
today vs seven days, note target, exact reminder time). The ideal-reading number is the ceiling the server allows — a
right answer exists for every phrasing when the planner reads intent and slots correctly; the live number depends on the
planner model and comes from `run_live_q100.py`. `results/` holds the graded runs (`before_*`, `pr16_*`, `after_*`).

Second-round fixes: forecast answers lead with a verdict (and "maximum by <date>" is searched on the queue model, two
options are compared side by side); prioritised lists restricted to a stage, grouped by customer, ranked by delivery risk,
or for a due date N days ago; required daily pace for two orders; all customers ranked when none is named; a customer-level
"anything to act on?" summary; a one-stage focus verdict; trace questions state what the record holds; clock-time reply
deadlines; "draft … and send it" previews; "ok" with nothing pending; the degraded draft carries the manager's question.

## Similar Questions tab (grounding, n = 300)

| Run (ideal reading) | PASS | PARTIAL | FAIL |
|---|---|---|---|
| Before (main at PR #17) | 113 (38%) | 124 | 63 (26 of them server errors on unknown order IDs) |
| After the grounding layer (9 Nov) | **300 (100%)** | 0 | 0 |
| Keyword fallback, after | 76 (25%) | 219 | 5 (misroutes without the model; no sends) |

`WorkflowEngine.grounding_check` runs before every intent (including chases and the overview): an order number not on
file in any spelling ("ORD-244", "order 218", "237 status?", "two one eight", "244 vs 286") → "There is no order … Order IDs
run ORD-001 to ORD-120"; a stage this factory does not have (cutting, sewing, embroidery, inspection…) → the four real
stages, plus the log's last date when a date is named; a product not on file ("jacket orders") or an order type the records
do not carry ("export", "uniform") → the products and customers on file; a customer not on file → the customers on file;
a workshop not on file (W9) → W1–W8; "the order from yesterday's meeting" → meetings are not in the records. Nothing is
drafted, saved, scheduled or compared on a missing entity, and a missing ID is not carried into the next turn. The original
sheet stays at 300/300.
