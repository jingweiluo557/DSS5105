# Held-out ground-truth test (Sprint 3, 9 Nov 2026)

70 questions the system had never seen, run **once**, no fixes in between. Reported in the Sprint 3 video.

**How the ground truth was made.** A separate author (an agent instructed to read only `data/*.csv`, never the backend,
the evaluation sets or the demo) wrote 70 questions the way a manager types them — "ord 62 due when?", "#81 what stage",
"is 83 or 2 more overdue" — in eight categories, using the system's documented rules (business date 2026-04-01; overdue =
in progress and due before today; normal = within min–max of the previous 8 same weekdays; actions preview first; never
write to customers). Every gold fact was computed twice by independent code — `gold/compute_a.py` (Python csv/datetime)
and `gold/compute_b.py` (SQLite SQL) — and `gold/build.py` refuses to write `heldout.json` unless the two agree.
Feasibility questions were left out: their gold needs the queue simulation itself.

**How it was run.** `run_heldout.py ideal` gives the engine the reading in `annotations_heldout.py` (what a correct
planner returns; written before the run) and measures the server: routing, tools, wording. `run_heldout.py fallback`
uses the keyword planner the product falls back to without a model. Each item gets a fresh chat; for multi-turn items
only the last answer is graded.

**How it was graded.** Automatically against the gold tokens (`must_include`, `any_of`, `must_not_include`, expected
behaviour), then a manual audit of 10 verdicts that is listed in `run_heldout.py` (`AUDIT`) with the reason for each:
7 automatic PASSes were too generous (e.g. a stray "5" in a generic summary), 2 non-PASSes were wording the phrase list
lacked ("No customer named Patagonia…"), 1 reason corrected. `results/heldout_ideal.json` keeps both verdicts.

| Category | Ideal reading (audited) | Keyword fallback (automatic) |
|---|---|---|
| Production & normal range | 10/10 | 0/10 |
| Not in the records | 7/8 | 1/8 |
| Counts & totals | 8/10 | 4/10 |
| Actions (chase, remind) | 6/8 | 0/8 |
| Order lookup | 7/10 | 6/10 |
| Follow-ups (2–3 turns) | 4/8 | 0/8 |
| Rankings | 3/8 | 0/8 |
| Comparisons | 3/8 | 4/8 |
| **Total** | **48/70 (69%)**, 14 partial, 8 wrong; 95% Wilson interval 57–78% | **15/70 (21%)** |

No email was sent in any run (every chase stops at a preview; the fallback never drafts at all).

With 8–10 items per category, a difference of one or two questions between categories is within noise; read the
category rows as indicative and the total as the result.

## What breaks it (the 22 non-PASS items, ideal reading)

| Count | Failure | Items |
|---|---|---|
| 9 | A ranking/filter the tools don't have: order date, "fewest", stage-filtered idle, "next due after today", date-range count, "finished in March", totals over a list, soonest within a customer, most pieces as a direct answer | A05 A08 M03 M06 R02 R04 R05 R06 R08 |
| 7 | Order numbers the parser can't read: "#81", "#2", "#83", "81 or 66", "83 or 2", "053 or 036", bare "002" | C03 C04 L05 L10 M02 X03 X07 |
| 3 | Comparison without a verdict (stage tables) / two customers written in lower case with "&" | C02 C07 C08 |
| 3 | "who's it for?" after a ranked list; lookup gives the due date but not "overdue"; a workshop that isn't on file (SilkRoute) gets a draft — nothing sent | M01 L03 N07 |

## Next fixes, by misses removed
1. One sort-and-filter tool over any order field (order date, due date, idle days, pieces; stage/customer filter; ascending or descending; "after today"), with totals — 9.
2. Read "#81", "83 or 2", bare zero-padded numbers as order IDs when the number is on file — 7.
3. A one-line verdict under every comparison table — 3.
4. Run these 70 on the live model to measure the planner itself, which this run does not:

   ```
   THREADPILOT_TOKEN=<workspace access key> python run_live_heldout.py --base https://<backend>
   ```

   The key is read from the environment only (never commit it). Same grader as `run_heldout.py`; nothing is sent
   (chase-ups stop at the preview). Writes `results/heldout_live.json`; audit the non-PASS rows by hand before reporting.

## 14 Nov: the fixes, and a regression run (not a new accuracy)
Fixes 1–3 above are in (`backend/app/services/set_questions.py`, `order_refs.py`, the comparison and ranking branches of
`workflow_engine.py`, `conversation_memory.py`; tests in `backend/tests/test_heldout_fixes.py`, most with a sibling
question worded differently and the expected value computed in the test from `orders.csv`).

| Run on the same 70 | 9 Nov (first, unseen) | 14 Nov (after the fixes) |
|---|---|---|
| Ideal reading, audited | 48 pass · 14 partial · 8 fail | 70 pass |
| Keyword fallback | 15 pass · 40 partial · 15 fail | 26 pass · 29 partial · 15 fail |

```
python run_heldout.py ideal regression_2026-11-14      # results/regression_2026-11-14_ideal.json
python run_heldout.py fallback regression_2026-11-14
```

Read this table with three cautions.
1. **The 14 Nov column is a regression check, not held-out accuracy.** The fixes were written after reading these 70
   answers, so the questions are no longer unseen. The number to quote for "how accurate on questions it has not seen"
   is still 48/70 (69%, 95% interval 57–78%) until a fresh set is written and run once. The frozen first run stays in
   `results/heldout_ideal.json` and `results/heldout_fallback.json`; the planner readings in `annotations_heldout.py`
   were not changed.
2. **Three passes are by reading, not by the automatic phrase list** (N07, N08, M08; listed in `AUDIT_REGRESSION` with
   the reason). All 70 answers were read against the gold text by the same person who wrote the fixes; a second reader
   has not checked them.
3. **The planner is still not measured.** Both columns hand the server a correct reading of each question. The live
   model run (step 4 above) is still to do.

Other suites after the fixes: the two 300-question sheets stay at 300/300 (`evaluation/q100`), the 88-scenario replay
at 88/88 with every stated number traced to a tool result (`run_annotated_eval.py`, `score.py --strict`).
