# Sprint 1 presentation (5 minutes live, 2 minutes Q&A)

[`Presentation_GroupNN_Sprint1.pptx`](Presentation_GroupNN_Sprint1.pptx): 8 slides plus 5 backup slides. The 8 main slides take about 4 minutes
when spoken (a timed script is in each slide's speaker notes), which leaves about a minute before the hard stop at 5:00. Edit it in PowerPoint:
the text, shapes, tables and the chart are native, and the screenshots are real pictures of the running demo ([`screens/`](screens/), made by
[`scripts/capture_screenshots.py`](../../scripts/capture_screenshots.py), which types the questions into the real chat box; nothing is mocked up).

**File name.** The course requires `Presentation_GroupNN_Sprint1.pptx` (or `.pdf`), where NN is the two-digit group number, capitalised exactly,
and says non-conforming names lose marks. The file here keeps the letters `NN` as a placeholder because the repository does not hold the group
number. Before uploading, rename it: group 7 is `Presentation_Group07_Sprint1.pptx`. Upload by **3:00 PM on Friday 16 October 2026**, to the group's
Canvas folder with no subfolders.

## Follows the course's order

The Sprint 1 review (Capstone_Project_Spec_v5, "Sprint 1 review") asks for six things "clearly and in order"; the example deck
(DSS5105_Sprint_Review_Example) shows the structure.

| The course asks for | Slide |
|---|---|
| 1. Problem statement and proposed solution, including an architecture diagram (the example shows an agentic LLM) | 2 (problem and solution), 3 (architecture) |
| 2. Business value | 2 |
| 3. Sprint 1 progress (optional) | 4 (early wins), 5 (what was measured) |
| 4. Risk assessment (probability, impact, mitigation) | 6 |
| 5. Key assumptions (validation required, risk level, dependency) | 7 |
| 6. Sprint 2 development roadmap, including success criteria | 8 |
| Backup, for Q&A | 9 tool set and its edges, 10 actions need a confirmation, 11 the 12 first-pass failures, 12 an estimate and a watch that fires, 13 ready for a phone and a shared link (morning email in Outlook) |

Slide 1 is the title. Track 2's "declare your objective" instruction does not apply to Track 1.

Rule used to write it: **a number goes on a slide only if a file in this repository states it, or it is visible in a screenshot.** Anything the team
does not have yet is a yellow **ADD:** or **TEAM:** tag on the slide, never a guess.

## Where every number on the slides comes from

| Slide | Claim | Source |
|---|---|---|
| 1 | The morning page of Thursday 9 April 2026 (simulated day 8) | [`screens/01_briefing.png`](screens/01_briefing.png) |
| 2 | The five timed questions (7:00, 9:40, 11:15, 14:30, 17:00) and "the planner's half hour every morning, plus every 'let me check and call you back'" | Capstone_Project_Tracks_v4, Track 1 (the course's own brief) |
| 2 | "5 / 5": each of the five questions is answered by a tool in the demo | [conversation_scenarios.md](../conversation_scenarios.md): S1 (7:00), S2 (9:40), S5 (11:15), S6 (14:30), S7 (17:00) |
| 2 | Time saved is not measured | Nothing in the repository records a real user; see "What the repository cannot supply" below |
| 2 | In simulation, about 30 working days of lateness avoided per two months (95%: 18 to 43) | [business_value.md](../business_value.md) |
| 2, 3 | The morning email is written from the briefing and opens in Outlook filled in; the manager sends it | [outlook_setup.md](../outlook_setup.md); `frontend/dashboard.js`, `frontend/outlook.js` |
| 3 | Five tool kinds; the human gate (preview, confirm, log); the model never computes a number or writes a refusal; memory is the order in focus and any pending action | [tool_spec.md](../tool_spec.md); [tool_boundaries.md](../tool_boundaries.md), rules 1 to 4; `backend/app/schemas.py` (`state.active_order`, `state.pending_action`) |
| 3 | 120 orders, 360 production-log rows, 8 workshops | [`data/`](../../data/): `orders.csv`, `production_log.csv`, `workshops.csv` |
| 3 | Discovery also runs at 07:00 without being asked | [alert_triggers.md](../alert_triggers.md), the table at the top |
| 3 | "Normal" = previous 8 same weekdays plus or minus a band | [tool_spec.md](../tool_spec.md), "Definitions the tools share" |
| 4 | All 6 active TrendCart orders stopped moving (shared cause, not the queue) | [`briefings/2026-04-09.json`](../../briefings/2026-04-09.json), `headline`; [alert_triggers.md](../alert_triggers.md), `customer_stalled` |
| 4 | Discovery found 5 of 5 planted events, 1 to 4 days after each started (re-run after the 3-sigma + CUSUM change) | [README.md](../../../README.md), "Briefing, simulator and predictions" |
| 4 | A vague question that asks which of six orders; a refusal (revenue); the washing drop (297 against a usual 733) | [`screens/02`, `04`](screens/); [conversation_scenarios.md](../conversation_scenarios.md) (S2, S4) |
| 4 | Nine scenario scripts exposed six follow-ups that lost the thread; fixed and tested | [conversation_scenarios.md](../conversation_scenarios.md), "What recording these found"; `tests/test_chat.py` |
| 5 | First pass 24 of 36 (67%; first reported as 25 until a false pass was found), held-out 18 of 21 (86%), first-pass by category; bait questions 10 of 16; 3 of 163 numbers untraced | [evaluation.md](../evaluation.md), "Results: dashboard chat" and "Invented numbers" |
| 5 | Live backend: 36 of 45 scripted turns passed on the first full batch (7 hit HTTP 429); **not yet run on the 36 questions** | [live_model_verification.md](../live_model_verification.md); [evaluation.md](../evaluation.md), "Results: the live backend" |
| 6 | Risk 1: 3 of 163 stated numbers untraced, 1 a real error, fixed | [evaluation.md](../evaluation.md), "Invented numbers" |
| 6 | Risk 2: 15-minute single-use key, every action logged, the chat cannot cancel, delete or change an order; the morning email is sent only by the manager, from their own Outlook | [tool_spec.md](../tool_spec.md), "How actions stay safe"; [actions_and_limits.md](../actions_and_limits.md); [outlook_setup.md](../outlook_setup.md) |
| 6 | Risk 3: one briefing at 07:00; stage alerts about 2 false alarms a month (3-sigma + CUSUM) against 12 for the old band | [spc_detection.md](../spc_detection.md) |
| 6 | Risk 4: synthetic data, the team's own simulator, the team's own questions | [evaluation.md](../evaluation.md), "Limits"; [prediction_validation.md](../prediction_validation.md) |
| 6 | The **probability and impact ratings** are the drafter's judgement, not measured | See the checklist below |
| 6 | Risk 5: at most 40 model questions a minute per visitor on the public link | `CHAT_REQUESTS_PER_MINUTE` (default 40); [FEATURE_STATUS.md](../FEATURE_STATUS.md), "Ready for a public link" |
| 7 | "Today every question is asked on 1 April 2026"; the forecast is no better than repeating the last period | [failure_analysis.md](../failure_analysis.md), last section; [prediction_validation.md](../prediction_validation.md), section 3 |
| 7 | The **risk levels** are the drafter's judgement, not measured | See the checklist below |
| 8 | Pull request #4 merges with no conflicts and all tests pass on the merged code (198 and 136); then redeploy and run one database step ([CLOUDBASE_UPDATE_20261012.md](../CLOUDBASE_UPDATE_20261012.md)); the two feasibility methods can disagree | [FEATURE_STATUS.md](../FEATURE_STATUS.md); [tool_boundaries.md](../tool_boundaries.md), "Where our own tools disagree" |
| 8 | **Success criteria** (live first pass reported as run, 70% on blind questions, no unsourced number, public links, an owner per feature) | **Proposed**, drawn from the repository's own results (67% first pass) and the course's Sprint 2 rule that the GitHub and demo links are public and on the first slide; the team has not agreed them |
| 8 | Sprint 1 Fri 16 Oct, Sprint 2 Fri 30 Oct, Sprint 3 Fri 13 Nov, final zip Sun 15 Nov 2026 | Capstone_Project_Spec_v5 |
| 9 | 37 tools (18 live, 19 dashboard); 27 boundary questions | [tool_spec.md](../tool_spec.md); [tool_boundaries.md](../tool_boundaries.md) |
| 10 | Confirmation card with the worst case; chase logged, nothing sent; "Delete ORD-005" refused; 15-minute key | [`screens/06`, `07`](screens/); [actions_and_limits.md](../actions_and_limits.md) |
| 11 | The 12 first-pass failures, by cause (5, 6, 1), the three found by probing and the bait failures | [failure_analysis.md](../failure_analysis.md) |
| 13 | The email dialog on a 390 px phone and a laptop; no page scrolls sideways from 320 to 390 px (the briefing page was 878 px wide on a 390 px phone); 40 questions a minute per visitor; a rejected key says so; cover photo 2.4 MB to 195 KB; 198 and 136 tests pass on the merged code | [`screens/09`, `10`](screens/) (taken from the running app in its default, no-setup mode); `tests/test_phone_width.py`; [FEATURE_STATUS.md](../FEATURE_STATUS.md), "Ready for a public link" |
| 12 | Feasibility answer (800 hoodies by the 25th: finishes 28 April to 12 May, bottleneck Packing; range widened by 3 working days, see [calibration.md](../calibration.md)) and a watch that fires on 10 April | [`screens/05`, `08`](screens/); [conversation_scenarios.md](../conversation_scenarios.md) (S5, S7) |

The first-pass and held-out figures are for the **dashboard chat** (built-in tools, no language model). The discovery and feasibility figures
come from the team's own simulator, so they show internal consistency, not real-world accuracy. The slides say both.

## Before presenting (things only the team can supply)

- [ ] **Rename the file** to `Presentation_Group<NN>_Sprint1.pptx` with the two-digit group number, and upload it by 3:00 PM Fri 16 Oct.
- [ ] Title slide: **group number** and the **sixth team member's name** (the yellow tag).
- [ ] Slide 8: an **owner for each roadmap row**, and **agree the success criteria** (the yellow tag). The 70% target is a proposal.
- [ ] Slides 6 and 7: the **probability, impact and risk-level ratings** were drafted from the repository's evidence. Agree or change them.
- [ ] Run the live-backend evaluation **once** and replace "Not yet run on these 36 questions" on slide 5 with that number, reported as first pass
      ([how](../evaluation.md#results-the-live-backend-openai-model--mysql)). Do not re-run and report the better number.
- [ ] Each teammate adds at least 10 evaluation questions of their own, with the answer looked up in the CSV
      ([`evaluation/team_questions.example.json`](../../evaluation/team_questions.example.json)).
- [ ] Time one full run-through. The 8 main slides are written for about 4 minutes; Sprint reviews are hard stops at 5:00.
- [ ] Decide whether to show per-person contributions. Nothing in the repository records them, so the deck has none.

## What the repository cannot supply, so the slides do not claim it

Feedback from a real general manager, and any measured time saved. Slide 2 says so; slide 7 lists it as an assumption.

## Demo on the day

Slide 4's speaker notes say what to run; the full prompt order is in [FEATURE_STATUS.md](../FEATURE_STATUS.md). They run on the briefing demo
([`demo/briefing_demo.html`](../../demo/briefing_demo.html), no installation, no key) on 9 April. In the app it is **Morning Briefing** in the left
menu once this branch is merged and the site is redeployed. Say plainly that the demo chat uses built-in tools, not a language model.
