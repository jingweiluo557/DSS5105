# ThreadPilot evaluation — first-pass results

- Run: 2026-10-25T23:33:26.477219+00:00 against `in-process WorkflowEngine (CSV)` · model `annotated-planner` · business date 2026-04-01T12:00:00+08:00
- Eval set version 2026-10-26b: 83 questions/scenarios, 109 turns scored. Scored automatically; nothing fixed between run and score.

## Headline

| Metric | Result |
|---|---|
| Scenarios passed (all turns correct) | **83 / 83 (100%)** |
| Turns passed | 109 / 109 (100%) |
| Numbers stated in answers | 1782 |
| Numbers not traceable to a tool result or the user's words | **0** |

## By category

| Category | Scenarios passed | Turns passed |
|---|---|---|
| action | 6/6 | 11/11 |
| ambiguous | 6/6 | 6/6 |
| arithmetic_bait | 5/5 | 5/5 |
| discovery | 2/2 | 2/2 |
| facts | 12/12 | 12/12 |
| feasibility | 5/5 | 8/8 |
| judgement | 4/4 | 5/5 |
| multi_turn | 6/6 | 19/19 |
| sheet1 | 27/27 | 30/30 |
| tracing | 2/2 | 3/3 |
| unanswerable | 8/8 | 8/8 |

## Failures

## Untraced numbers (provenance check)

None.

## Passed

- F01 (facts): As of 2026-04-01: 34 orders in progress, 8 overdue (ORD-107, ORD-120, ORD-114, ORD-083, ORD-002, ORD-093, ORD-020, ORD-055), 1 due today, 2 
- F02 (facts): As of 2026-04-01: 34 orders in progress, 8 overdue (ORD-107, ORD-120, ORD-114, ORD-083, ORD-002, ORD-093, ORD-020, ORD-055), 1 due today, 2 
- F03 (facts): ORD-053 — UrbanThread, 800 Polo shirt; status IN_PROGRESS, stage ASSEMBLY, due 2026-04-10, last recorded activity 2026-03-31. Only last_acti
- F04 (facts): ORD-108 — Harbor Knits, 2000 Scarf; status IN_PROGRESS, stage ASSEMBLY, due 2026-04-03, last recorded activity 2026-03-31.
- F05 (facts): Recorded output on 2026-03-31 (Tuesday): assembly 455 pieces. Recorded stage output, not a judgement; ask whether it is normal to compare wi
- F06 (facts): Top 9 of 9 for 2026-04-01 to 2026-04-01 (overdue active orders first; business date 2026-04-01). Earlier due date first; ties: older last ac
- F07 (facts): As of 2026-04-01: 6 orders in progress, 2 overdue (ORD-120, ORD-020), 0 due today, 1 idle 5+ days; 3 of 11 completed orders on time (27.3%).
- F08 (facts): Recorded output on 2026-03-28 (Saturday): knitting 1031 pieces. Recorded stage output, not a judgement; ask whether it is normal to compare 
- F09 (facts): Active orders ranked by idle days (business date 2026-04-01). Most calendar days since last recorded activity first; ties by due date, then 
- F10 (facts): Top 14 of 14 for 2026-04-01 to 2026-04-08 (overdue active orders first; business date 2026-04-01). Earlier due date first; ties: older last 
- F11 (facts): Eligible outside workshops for accessories: W4 Little Loom (70/day, queue 0.5 d, pickup 1 d, defect batch risk 2%); W6 Nimble Needle (130/da
- F12 (facts): As of 2026-04-01: 34 orders in progress, 8 overdue (ORD-107, ORD-120, ORD-114, ORD-083, ORD-002, ORD-093, ORD-020, ORD-055), 1 due today, 2 
- J01 (judgement): Assembly on 2026-03-31: 455 pieces, below its normal range; the previous eight same weekdays ran 687–807 (mean 745.25), 39% below the mean. 
- J01b (judgement): Assembly on 2026-03-31: 455 pieces, below its normal range; the previous eight same weekdays ran 687–807 (mean 745.25), 39% below the mean.  | Assembly on 2026-03-31: 455 pieces, below its normal range; the previous eight same weekdays ran 687–807 (mean 745.25), 39% below the mean. 
- J02 (judgement): Washing on 2026-03-31: 732 pieces, within its normal range (normal); the previous eight same weekdays ran 617–774 (mean 708.75), 3% above th
- J03 (judgement): The record shows 657 pieces on 2026-03-31, not 800. Packing on 2026-03-31: 657 pieces, within its normal range (normal); the previous eight 
- T01 (tracing): Assembly on 2026-03-31: 455 pieces, below its normal range; the previous eight same weekdays ran 687–807 (mean 745.25), 39% below the mean.  | Assembly on 2026-03-31: 455 pieces, below its normal range; the previous eight same weekdays ran 687–807 (mean 745.25), 39% below the mean. 
- T02 (tracing): ORD-002 — Cotton Club, 1000 Crewneck sweater; status IN_PROGRESS, stage WASHING, due 2026-03-29, last recorded activity 2026-03-23. Already 
- M01 (multi_turn): Several matching orders. Which order ID, quantity or due date? ORD-120: Vest, 1500 pieces, due 2026-03-17; ORD-020: Vest, 1200 pieces, due 2 | ORD-005 — TrendCart, 500 Scarf; status IN_PROGRESS, stage KNITTING, due 2026-04-20, last recorded activity 2026-03-24. | ORD-005 — TrendCart, 500 Scarf; status IN_PROGRESS, stage KNITTING, due 2026-04-20, last recorded activity 2026-03-24. Not past due, not del | ORD-005 — TrendCart, 500 Scarf; status IN_PROGRESS, stage KNITTING, due 2026-04-20, last recorded activity 2026-03-24. Not past due, not del
- M02 (multi_turn): Which aspect matters: due date, stage, latest activity, status, pieces or overall delivery risk? | | Order | due_date | last_activity_date | | --- | --- | --- | | ORD-108 | 2026-04-03 | 2026-03-31 | | ORD-103 | 2026-04-04 | 2026-03-30 | | | Order | due_date | last_activity_date | | --- | --- | --- | | ORD-108 | 2026-04-03 | 2026-03-31 | | ORD-103 | 2026-04-04 | 2026-03-30 | Tr
- M03 (multi_turn): ORD-053 — UrbanThread, 800 Polo shirt; status IN_PROGRESS, stage ASSEMBLY, due 2026-04-10, last recorded activity 2026-03-31. | ORD-053 — UrbanThread, 800 Polo shirt; status IN_PROGRESS, stage ASSEMBLY, due 2026-04-10, last recorded activity 2026-03-31. Only last_acti | ORD-053 — UrbanThread, 800 Polo shirt; status IN_PROGRESS, stage ASSEMBLY, due 2026-04-10, last recorded activity 2026-03-31. Only last_acti
- M04 (multi_turn): Due today only, or include the next seven days? Overdue active orders will be included. | Top 14 of 14 for 2026-04-01 to 2026-04-08 (overdue active orders first; business date 2026-04-01). Earlier due date first; ties: older last  | Top 14 of 14 for 2026-04-01 to 2026-04-08 (overdue active orders first; business date 2026-04-01). Earlier due date first; ties: older last 
- A01 (ambiguous): Several matching orders. Which order ID, quantity or due date? ORD-114: Hoodie, 2000 pieces, due 2026-03-23; ORD-083: Hoodie, 1000 pieces, d
- A02 (ambiguous): Which order should I draft for? Please give its ID, or choose a summary draft.
- A03 (ambiguous): Several matching orders. Which order ID, quantity or due date? ORD-073: Hoodie, 400 pieces, due 2026-04-20; ORD-008: Polo shirt, 600 pieces,
- A04 (ambiguous): Which stage: knitting, assembly, washing or packing? Say "all four" to compare every stage. And which date, if not yesterday?
- A05 (ambiguous): Does the deadline mean ready at our factory or delivered to the customer?
- A06 (ambiguous): Which order should I use? Please give its ID or customer.
- U01 (unanswerable): This system holds no prices, costs, revenue or margins: orders.csv records who ordered what, how many pieces and when. I can report counts, 
- U02 (unanswerable): The data has no worker, operator or shift records: production_log.csv holds factory-wide pieces per stage per day only. I can show the stage
- U03 (unanswerable): There is no order ORD-999 in the current records. Order IDs run ORD-001 to ORD-120; check the number or give the customer and product instea
- U04 (unanswerable): Assembly on 2026-03-25: 394 pieces, below its normal range; the previous eight same weekdays ran 702–901 (mean 803.5), 51% below the mean. S
- U05 (unanswerable): No orders recorded for customer 'Zara'. Customers on file: Bright Basics, Cotton Club, Harbor Knits, Loom & Leaf, Maple & Co, Northwind Appa
- U06 (unanswerable): ORD-005 — TrendCart, 500 Scarf; status IN_PROGRESS, stage KNITTING, due 2026-04-20, last recorded activity 2026-03-24. Only last_activity_da
- U07 (unanswerable): I cannot delete or modify orders: the chat reads the order records and can only draft a chase-up, save an internal note or set a reminder, e
- U08 (unanswerable): This system holds no prices, costs, revenue or margins: orders.csv records who ordered what, how many pieces and when. I can report counts, 
- Fe01 (feasibility): Does the deadline mean ready at our factory or delivered to the customer? | Conditional forecast, not a promise: {   "due_date": "2026-04-25",   "delivery_point": "customer",   "available_workdays": 21,   "delivery_b | Conditional forecast, not a promise: {   "due_date": "2026-04-25",   "delivery_point": "customer",   "available_workdays": 21,   "delivery_b | Conditional forecast, not a promise: {   "due_date": "2026-04-25",   "delivery_point": "customer",   "available_workdays": 21,   "delivery_b
- Fe02 (feasibility): Conditional forecast, not a promise: {   "due_date": "2026-04-15",   "delivery_point": "customer",   "available_workdays": 12,   "delivery_b
- Fe03 (feasibility): Does the deadline mean ready at our factory or delivered to the customer?
- Fe04 (feasibility): Eligible outside workshops for tops, 250-piece batch: W6 Nimble Needle (130/day, queue 1.0 d, pickup 1 d, defect batch risk 5%, about 3.9 da
- Fe05 (feasibility): ORD-017: later. Less than two order-working-days of lateness saved for this order or across the queue. Finish: 2026-04-22 → 2026-04-08. Late
- Ac01 (action): Draft 1 · To: production planner Department: WASHING Subject: ThreadPilot chase-up | ORD-002 Please check the current status and confirm the | Draft 1 · To: production planner Department: WASHING Subject: ThreadPilot chase-up | ORD-002 Please check the current status and confirm the | To: production planner Department: WASHING Subject: ThreadPilot chase-up | ORD-002  Please check the current status and confirm the next ste
- Ac02 (action): Internal note for ORD-002, business date 2026-04-01: escalated with the planner today Please confirm to save. It will not be sent externally | Internal note saved to ORD-002 with timestamp. It was not sent externally.
- Ac03 (action): Create reminder for ORD-002 at 2026-04-02T14:00:00+08:00: notify only if no_activity is still unmet in recorded data. Please confirm. | Reminder created for ORD-002: at 2026-04-02T14:00:00+08:00 you will be notified only if no activity is still the case. Nothing is sent outsi
- Ac04 (action): I cannot cancel orders or contact customers: order changes are made in the factory system, and the chat only drafts internal chase-ups, note
- Ac05 (action): I cannot send without showing you the draft first: every send needs a preview and your confirmation. Here is the draft: Draft 1 · To: planne
- Ac06 (action): Draft 1 · To: planner Department: ASSEMBLY Subject: ThreadPilot chase-up | ORD-120 Please check the current status and confirm the next step | As of 2026-04-01: 34 orders in progress, 8 overdue (ORD-107, ORD-120, ORD-114, ORD-083, ORD-002, ORD-093, ORD-020, ORD-055), 1 due today, 2 
- AR01 (arithmetic_bait): As of 2026-04-01: 34 orders in progress, 8 overdue (ORD-107, ORD-120, ORD-114, ORD-083, ORD-002, ORD-093, ORD-020, ORD-055), 1 due today, 2 
- AR02 (arithmetic_bait): As of 2026-04-01: 34 orders in progress, 8 overdue (ORD-107, ORD-120, ORD-114, ORD-083, ORD-002, ORD-093, ORD-020, ORD-055), 1 due today, 2 
- AR03 (arithmetic_bait): | Order | pieces | product | | --- | --- | --- | | ORD-108 | 2000 | Scarf | | ORD-061 | 800 | Scarf |
- AR04 (arithmetic_bait): That is not something this system can answer from its data: it holds orders, daily stage output and workshop profiles only. Ask about an ord
- AR05 (arithmetic_bait): As of 2026-04-01: 6 orders in progress, 2 overdue (ORD-120, ORD-020), 0 due today, 1 idle 5+ days; 3 of 11 completed orders on time (27.3%).
- M05 (multi_turn): ORD-020 — TrendCart, 1200 Vest; status IN_PROGRESS, stage WASHING, due 2026-03-31, last recorded activity 2026-03-30. | ORD-120 — TrendCart, 1500 Vest; status IN_PROGRESS, stage ASSEMBLY, due 2026-03-17, last recorded activity 2026-03-30. | ORD-120 — TrendCart, 1500 Vest; status IN_PROGRESS, stage ASSEMBLY, due 2026-03-17, last recorded activity 2026-03-30. Already overdue: due 
- M06 (multi_turn): Does the deadline mean ready at our factory or delivered to the customer? | As of 2026-04-01: 34 orders in progress, 8 overdue (ORD-107, ORD-120, ORD-114, ORD-083, ORD-002, ORD-093, ORD-020, ORD-055), 1 due today, 2  | Conditional forecast, not a promise: {   "due_date": "2026-04-25",   "delivery_point": "customer",   "available_workdays": 21,   "delivery_b
- D01 (discovery): 34 findings as of 2026-04-01 (1 stage drop, 2 will miss, 8 overdue, 23 high risk); top 5 by tier and score: 1. [P1] Assembly has been below 
- D02 (discovery): 5 findings as of 2026-04-01 (2 overdue, 3 high risk); top 5 by tier and score: 1. [P2] ORD-120 (TrendCart) is 15 days overdue, still at ASSE
- S01 (sheet1): Which one? 8 active orders are overdue as of 2026-04-01: ORD-107 (Northwind Apparel, 2000 Cardigan, packing, 16 d overdue); ORD-120 (TrendCa
- S02 (sheet1): ORD-093 — Maple & Co, 100 Beanie; status IN_PROGRESS, stage WASHING, due 2026-03-29, last recorded activity 2026-04-01. Already overdue: due
- S03 (sheet1): | Order | due_date | current_stage | last_activity_date | status | | --- | --- | --- | --- | --- | | ORD-005 | 2026-04-20 | KNITTING | 2026-
- S04 (sheet1): VIP status alone should not override an earlier firm commitment. The rule this system can apply: the earlier due date keeps priority unless 
- S05 (sheet1): Due today only, or include the next seven days? Overdue active orders will be included. | Top 3 of 9 for 2026-04-01 to 2026-04-01 (overdue active orders first; business date 2026-04-01). Earlier due date first; ties: older last ac
- S06 (sheet1): The system keeps no dated exception snapshots, so it cannot say what changed since yesterday. The archived 07:00 briefings hold each day’s c
- S07 (sheet1): Packing on 2026-03-31: 657 pieces, within its normal range (normal); the previous eight same weekdays ran 562–734 (mean 667.75), 2% below th
- S08 (sheet1): Which date is the 800-piece assembly figure for? ("today", "yesterday" or a date; I compare it with the same weekday in recent working weeks
- S09 (sheet1): 2026-02-31 is not a valid date (February 2026 has 28 days). Which date should I check? For example "yesterday", "31 March" or "2026-03-31".
- S10 (sheet1): 2026-02-15 was a Sunday: the factory is closed, no output is recorded for any stage, and a closed day is not compared with working-day level
- S11 (sheet1): No production record for 2026-04-01 yet (the log ends 2026-03-31); using 2026-03-31 (Tuesday). Assembly is the stage to worry about on 2026-
- S12 (sheet1): Assembly is the stage to worry about on 2026-03-31: knitting 905 (within 797–1018); assembly 455 (below 687–807, -39%, 6 working days below)
- S13 (sheet1): Production the last 3 working days (2026-03-28 to 2026-03-31): | Date | Assembly | | --- | --- | | 2026-03-28 Sat | 445 (below 687–918) | | 
- S14 (sheet1): Assembly is the stage to worry about on 2026-03-31: knitting 905 (within 797–1018); assembly 455 (below 687–807, -39%, 6 working days below) | No. Assembly has been below its same-weekday range for 6 consecutive working days, since 2026-03-25; 2026-03-31 was the latest of them, not 
- S15 (sheet1): Production since 2026-03-25 (to 2026-03-31, the latest record): | Date | Assembly | | --- | --- | | 2026-03-25 Wed | 394 (below 702–901) | |
- S16 (sheet1): Production late March (2026-03-21 to 2026-03-31): | Date | Assembly | | --- | --- | | 2026-03-21 Sat | 746 (within 687–918) | | 2026-03-22 S
- S17 (sheet1): Production since 2026-03-25 (to 2026-03-31, the latest record): | Date | Assembly | | --- | --- | | 2026-03-25 Wed | 394 (below 702–901) | | | Two baselines, both from production_log.csv, for since 2026-03-25 (to 2026-03-31, the latest record): 1. Same-weekday band: for each day in 
- S18 (sheet1): ORD-005 — TrendCart, 500 Scarf; status IN_PROGRESS, stage KNITTING, due 2026-04-20, last recorded activity 2026-03-24. Not past due, not del
- S19 (sheet1): Recorded output on 2026-03-31 (Tuesday) by stage: knitting 905; assembly 455; washing 732; packing 657 pieces. Stage outputs are not added t
- S20 (sheet1): No record can exist for 2026-04-03: the business date is 2026-04-01 and the log ends 2026-03-31. The question’s premise cannot be checked ye
- S21 (sheet1): Which TrendCart order should I chase? ORD-120 (TrendCart, 1500 Vest, assembly, 15 d overdue); ORD-020 (TrendCart, 1200 Vest, washing, 1 d ov
- S22 (sheet1): ORD-103 was last active 2026-03-30, 2 days ago, not a week. It is Bright Basics, 2000 Scarf, at assembly, due in 3 days, so it is not stalle
- S23 (sheet1): Which Maple & Co order? ORD-083 (Maple & Co, 1000 Hoodie, washing, 9 d overdue); ORD-093 (Maple & Co, 100 Beanie, washing, 3 d overdue). Giv
- S24 (sheet1): I cannot cancel or remove orders, or change the schedule: the chat reads the records and saves internal notes only. I can record the intent 
- S25 (sheet1): QuickStitch (W1) makes TOPS only; ORD-103 is ACCESSORIES (scarf). Record the note anyway, or choose another workshop? Active workshops that 
- S26 (sheet1): I can watch one condition per reminder: no new activity recorded for the order, or no reply to the chase-up. Which should this reminder chec
- S27 (sheet1): I cannot send without showing you the draft first: every send needs a preview and your confirmation. Who should receive the draft for ORD-10
