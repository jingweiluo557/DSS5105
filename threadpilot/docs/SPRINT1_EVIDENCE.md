# Sprint 1 claims and where their evidence lives now

The Sprint 1 deck (16 Oct 2026) cited files that were never committed to this repository. This page maps every quoted number or document to the file that backs it today, so nothing on a slide is unbacked. Where a claim is superseded by Sprint 2 work, the newer file is the one to quote.

| Slide claim | Cited then | Backed by now | Status |
|---|---|---|---|
| "24 of 36 right on the first try (67%)", 18/21 held-out, 10/16 bait held | `docs/evaluation.md` (dashboard chat, rule-based) | **Superseded** by `evaluation/` : 54 questions with code-computed answers, live first pass 29/47 (62%) on the deployed model, offline 54/54 after fixes (`evaluation/EVALUATION.md`, `REPORT_live_20261024.md`) | Quote the Sprint 2 numbers; the 36-question set is not in the repo |
| "3 of 163 numbers not traced to a tool; 1 a real error" | provenance check by hand | `evaluation/score.py` provenance check: 0/169 untraced live, 0/879 offline; `docs/NO_ARITHMETIC_PROOF.md` | Superseded, automated |
| "12 first-pass failures analysed one by one" | `docs/failure_analysis.md` | `evaluation/FAILURE_ANALYSIS.md` (18 live failures in six causes, with fixes and the after-fix status) | Superseded |
| "37 tools in one table: 18 live, 19 dashboard chat" | tool table | `docs/TOOL_SPECIFICATION.md` (25 live tools/services, one table in the brief's format); the 19 dashboard-chat tools belong to the simulator repository `footoonming/DSS5105_Track1` (`docs/chat_tools.md`, 18 rows) | Live set documented here; simulator set documented there |
| "27 boundary questions, each naming the tool that answers and the neighbour that must not" | `docs/tool_boundaries.md` | boundary questions are part of the evaluation set (facts vs judgement vs tracing, risk vs forecast vs capacity, draft vs send); the boundary paragraph closes `docs/TOOL_SPECIFICATION.md` | Covered differently |
| "Normal = previous 8 same weekdays ± the larger of 1.5 SD or 5%; Sundays closed" | judgement rule | Live backend: previous 8 same weekdays, **min–max** range (`workflow_tools.normality`); the ±1.5 SD band is the simulator's rule (`simulation/briefing.py` in the other repo) | Two definitions still exist across the two repos; the live one is the one quoted in `TOOL_SPECIFICATION.md` |
| "Stage alerts use 3-sigma + CUSUM: about 2 false alarms a month, against 12 for the old band" | `docs/alert_triggers.md` | **Superseded** by `docs/ALERT_POLICY.md`: sustained-drop rule (3 consecutive working days below the same-weekday minimum), tiers, cooldowns, caps; the 2-vs-12 figure cannot be reproduced from committed code and should not be quoted | Replace the claim |
| "Discovery found 5 of 5 planted events, 1–4 days after each began" | simulator evaluation | `simulation/evaluate_discovery.py` in `footoonming/DSS5105_Track1` | Lives in the other repo; cite it as such |
| "≈ S$29.6k net value a year" and the line items | `docs/business_case.md` | `docs/BUSINESS_CASE.md` (reconstructed from backup slide 15, labelled as estimates) | Committed |
| "198 and 136 tests pass on the merged code (PR #4)" | test counts | GitHub Actions now runs the backend suite and the offline evaluation on every push (`.github/workflows/threadpilot-backend.yml`); quote the badge/run, not a remembered count | Automated |
| "Checked 14 Oct: the cloud backend answers, model switched on" | manual check | `docs/CLOUDBASE_RELEASE_20261024.md` and the 24 Oct live transcript (`evaluation/transcript_live_20261024.json`) | Committed |
| "Phones: no page scrolls sideways at 320–390 px (tested)" | e2e test | `tests/e2e/` in this repo; the capacity chart was checked at 390 px on 26 Oct | Committed |

Rule for the Sprint 2 deck: every number on a slide names a file in this repository (or the simulator repository, explicitly) that produces it.
