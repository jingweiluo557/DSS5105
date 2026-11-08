# 100 questions × 3 contexts (sheet "100Q 3 Context Same Structure")

The team's 100-question sheet, each question phrased three ways (formal, rephrased, shorthand/typos), run through the
workflow engine as one running conversation per scenario per context (the sheet is written that way: 1.2 "refresh an
active order" refers to the order established in 1.1).

| File | What it is |
|---|---|
| `questions.json` | The sheet: no, scenario, field, the three phrasings, the sheet's expected answer where given, PIC. |
| `run_q100.py` | Offline run through `WorkflowEngine` with two planners: `ideal` (the intent and slots a careful reader would return per row, so it measures the server) and `fallback` (the keyword planner used when the model is down). Writes `answers_<mode>.json`. `Q100_SESSION=field` for the stricter one-session-per-field reading. |
| `run_live_q100.py` | The same questions over HTTP against a deployment (the real planner model). Token from `THREADPILOT_TOKEN` only. Writes `answers_live.json`. |
| `grade.py` | One rule per question (PASS / PARTIAL / FAIL) from the brief, the sheet's expected answers and the gold facts computed from the CSVs on 2026-04-01. Writes `*_graded.json` and prints totals by field. |
| `results/` | Graded runs before and after the 8 Nov 2026 fixes, ideal reading and keyword fallback. |

```bash
cd threadpilot/evaluation/q100
python run_q100.py ideal && python grade.py answers_ideal.json
python run_q100.py fallback && python grade.py answers_fallback.json
THREADPILOT_TOKEN=... python run_live_q100.py --base https://<backend> && python grade.py answers_live.json
```

## Result (ideal reading, n = 300)

| Run | PASS | PARTIAL | FAIL | Questions right in all 3 contexts |
|---|---|---|---|---|
| Before (code at PR #14) | 143 (48%) | 85 | 72 | 31 / 100 |
| After | 226 (75%) | 73 | 1 | 71 / 100 |
| Keyword fallback, before → after | 6 → 13 (2% → 4%) | 29 → 32 | 265 → 255 | 0 → 2 |

Context 1 / 2 / 3 after: 76 / 75 / 75 PASS of 100 each. The remaining PARTIALs are mostly one question too many
(window, which order of a customer, exact time), forecasts shown as JSON rather than a one-line verdict, and trace
questions the data cannot answer (one activity date per order). The ideal-reading number is the ceiling the server
allows; the live number depends on the planner model and comes from `run_live_q100.py`.
