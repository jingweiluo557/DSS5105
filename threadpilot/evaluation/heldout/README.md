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
