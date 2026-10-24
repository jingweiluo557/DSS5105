# ThreadPilot evaluation set and harness

The Track 1 deliverable the brief asks for: **an evaluation set of at least 30 questions with verified answers and measured accuracy** (≥5 ambiguous / unanswerable / bait, ≥5 feasibility or action). Everything here is reproducible from the three seed CSVs; no expected answer is typed by hand.

Suggested location in the team repo: `threadpilot/evaluation/`.

| File | What it is |
|---|---|
| `build_eval_set.py` | Computes every expected value from `data/*.csv` with the tools' own definitions and writes `eval_set.json` (47 questions, 66 turns, 8 categories, gold values + evidence rows). Edit this file to add questions. |
| `eval_set.json` | The evaluation set: per-turn machine-checkable expectations plus the gold block. |
| `EVALUATION.md` | Human-readable table: question → verified answer → latest first-pass result. |
| `run_annotated_eval.py` + `annotations.py` | Offline regression: drives `WorkflowEngine.converse()` with the classification an ideal planner would emit per turn (no model, no network, seconds). Tests the server alone; writes `transcript_annotated.json`. |
| `run_live_eval.py` | Runs the set over HTTP against a backend (`POST /api/v1/workflow/chat`, token in `THREADPILOT_TOKEN`), one fresh session per question, carrying `confirmation_id` like the frontend does. Writes `transcript_*.json`. |
| `make_browser_batches.py` | Alternative runner for when the backend is not reachable from your machine: emits JS snippets that run inside the signed-in ThreadPilot page using `window.threadpilotFetch` (the token never leaves the browser). |
| `score.py` | Automatic scorer → `results_*.json` + `REPORT_*.md`. Checks: intent, clarification/confirmation flags, required facts (with date-format alternatives), forbidden claims, forbidden executions, no order committed on ambiguity, and the **invented-number check** (every 2+ digit number or date in the answer must appear in a tool result, the evidence, or the manager's own words). |
| `verify_tool_results.py` | Cross-checks the deterministic tool outputs captured in a transcript (counts, prioritisation order, normality ranges, capacity arithmetic, risk fields) against the independent gold computation. |
| `transcript_live_20261024.json`, `results_live_20261024.json`, `REPORT_live_20261024.md` | The 24 Oct 2026 first pass against the CloudBase deployment (`gpt-6-luna`). |
| `FAILURE_ANALYSIS.md` | The 18 failures grouped by root cause, with fixes, plus two findings outside the scoring. |

## Reproduce

```bash
python build_eval_set.py --data ../data --out eval_set.json          # gold + questions
python run_annotated_eval.py && python score.py --eval eval_set.json --transcript transcript_annotated.json --out results_annotated.json --report REPORT_annotated.md
THREADPILOT_TOKEN=... python run_live_eval.py --base https://<backend> --out transcript.json
python score.py --eval eval_set.json --transcript transcript.json --out results.json --report REPORT.md
python verify_tool_results.py --eval eval_set.json --transcript transcript.json
python make_evaluation_table.py --eval eval_set.json --results results.json --out EVALUATION.md
```

## Rules we held ourselves to

- **First pass only.** Run once, score, report. Fixing a route and re-running produces a second number labelled as such; it never replaces the first.
- **Gold = code, not a person.** `build_eval_set.py` is the only source of expected values; a disagreement between a tool and the gold is investigated in `verify_tool_results.py`, not patched in the question.
- **Honest refusals pass, non-answers fail.** "This system holds no price data" passes U01; "Which order or operation would you like to check?" does not.
- **Design choices are scored as the spec says.** Where the dialogue spec deliberately asks (compare → "which aspect?", attention → "today or seven days?"), the expectation is the clarification; where the spec says to ask and the system guessed, that is a failure.
- **Writes are real.** The note (Ac02) and reminder (Ac03) scenarios write to the live demo database on confirmation; the chase scenarios stop at the confirmation preview and never say "send now".

## Categories (brief requirement in brackets)

facts 12 · judgement 4 · tracing 2 · multi-turn 4 · ambiguous 6 + unanswerable/bait 8 (≥5) · feasibility 5 + action 6 (≥5)
