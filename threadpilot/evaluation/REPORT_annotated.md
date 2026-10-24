# ThreadPilot evaluation — first-pass results

- Run: 2026-10-24T08:30:56.886913+00:00 against `in-process WorkflowEngine (CSV)` · model `annotated-planner` · business date 2026-04-01T12:00:00+08:00
- Eval set version 2026-10-24: 47 questions/scenarios, 66 turns. Scored automatically; nothing fixed between run and score.

## Headline

| Metric | Result |
|---|---|
| Scenarios passed (all turns correct) | **47 / 47 (100%)** |
| Turns passed | 66 / 66 (100%) |
| Numbers stated in answers | 879 |
| Numbers not traceable to a tool result or the user's words | **0** |

## By category

| Category | Scenarios passed | Turns passed |
|---|---|---|
| action | 6/6 | 11/11 |
| ambiguous | 6/6 | 6/6 |
| facts | 12/12 | 12/12 |
| feasibility | 5/5 | 8/8 |
| judgement | 4/4 | 5/5 |
| multi_turn | 4/4 | 13/13 |
| tracing | 2/2 | 3/3 |
| unanswerable | 8/8 | 8/8 |

## Failures

## Untraced numbers (provenance check)

None.

## Passed

- F01 (facts): {"total_orders": 120, "by_stage": {"COMPLETE": 86, "ASSEMBLY": 10, "PACKING": 2, "WASHING": 10, "KNITTING": 12}, "by_status": {"COMPLETE": 8
- F02 (facts): {"total_orders": 120, "by_stage": {"COMPLETE": 86, "ASSEMBLY": 10, "PACKING": 2, "WASHING": 10, "KNITTING": 12}, "by_status": {"COMPLETE": 8
- F03 (facts): ORD-053 — UrbanThread, 800 Polo shirt; status IN_PROGRESS, stage ASSEMBLY, due 2026-04-10, last recorded activity 2026-03-31. Only last_acti
- F04 (facts): ORD-108 — Harbor Knits, 2000 Scarf; status IN_PROGRESS, stage ASSEMBLY, due 2026-04-03, last recorded activity 2026-03-31.
- F05 (facts): Recorded output on 2026-03-31 (Tuesday): assembly 455 pieces. Recorded stage output, not a judgement; ask whether it is normal to compare wi
- F06 (facts): Business date: 2026-04-01. Review window: 2026-04-01 through 2026-04-01 (including overdue active orders). Earlier due date first; ties: old
- F07 (facts): {"total_orders": 17, "by_stage": {"COMPLETE": 11, "ASSEMBLY": 1, "WASHING": 1, "KNITTING": 4}, "by_status": {"COMPLETE": 11, "IN_PROGRESS": 
- F08 (facts): Recorded output on 2026-03-28 (Saturday): knitting 1031 pieces. Recorded stage output, not a judgement; ask whether it is normal to compare 
- F09 (facts): Active orders ranked by idle days (business date 2026-04-01). Most calendar days since last recorded activity first; ties by due date, then 
- F10 (facts): Business date: 2026-04-01. Review window: 2026-04-01 through 2026-04-08 (including overdue active orders). Earlier due date first; ties: old
- F11 (facts): Eligible outside workshops for accessories: W4 Little Loom (70/day, queue 0.5 d, pickup 1 d, defect batch risk 2%); W6 Nimble Needle (130/da
- F12 (facts): {"total_orders": 120, "by_stage": {"COMPLETE": 86, "ASSEMBLY": 10, "PACKING": 2, "WASHING": 10, "KNITTING": 12}, "by_status": {"COMPLETE": 8
- J01 (judgement): Recorded facts and labelled interpretation: {   "stage": "ASSEMBLY",   "date": "2026-03-31",   "output": 455,   "baseline_records": [     { 
- J01b (judgement): Recorded facts and labelled interpretation: {   "stage": "ASSEMBLY",   "date": "2026-03-31",   "output": 455,   "baseline_records": [     {  | Recorded facts and labelled interpretation: {   "stage": "ASSEMBLY",   "date": "2026-03-31",   "output": 455,   "baseline_records": [     { 
- J02 (judgement): Recorded facts and labelled interpretation: {   "stage": "WASHING",   "date": "2026-03-31",   "output": 732,   "baseline_records": [     {  
- J03 (judgement): Recorded facts and labelled interpretation: {   "stage": "PACKING",   "date": "2026-03-31",   "output": 657,   "baseline_records": [     {  
- T01 (tracing): Recorded facts and labelled interpretation: {   "stage": "ASSEMBLY",   "date": "2026-03-31",   "output": 455,   "baseline_records": [     {  | Recorded facts and labelled interpretation: {   "stage": "ASSEMBLY",   "date": "2026-03-31",   "output": 455,   "baseline_records": [     { 
- T02 (tracing): ORD-002 — Cotton Club, 1000 Crewneck sweater; status IN_PROGRESS, stage WASHING, due 2026-03-29, last recorded activity 2026-03-23. Already 
- M01 (multi_turn): Several matching orders. Which order ID, quantity or due date? ORD-120: Vest, 1500 pieces, due 2026-03-17; ORD-020: Vest, 1200 pieces, due 2 | ORD-005 — TrendCart, 500 Scarf; status IN_PROGRESS, stage KNITTING, due 2026-04-20, last recorded activity 2026-03-24. | ORD-005 — TrendCart, 500 Scarf; status IN_PROGRESS, stage KNITTING, due 2026-04-20, last recorded activity 2026-03-24. Not past due: due 202 | ORD-005 — TrendCart, 500 Scarf; status IN_PROGRESS, stage KNITTING, due 2026-04-20, last recorded activity 2026-03-24. Not past due: due 202
- M02 (multi_turn): Which aspect matters: due date, stage, latest activity or status? | | Order | due_date | last_activity_date | | --- | --- | --- | | ORD-108 | 2026-04-03 | 2026-03-31 | | ORD-103 | 2026-04-04 | 2026-03-30 | | | Order | due_date | last_activity_date | | --- | --- | --- | | ORD-108 | 2026-04-03 | 2026-03-31 | | ORD-103 | 2026-04-04 | 2026-03-30 | Tr
- M03 (multi_turn): ORD-053 — UrbanThread, 800 Polo shirt; status IN_PROGRESS, stage ASSEMBLY, due 2026-04-10, last recorded activity 2026-03-31. | ORD-053 — UrbanThread, 800 Polo shirt; status IN_PROGRESS, stage ASSEMBLY, due 2026-04-10, last recorded activity 2026-03-31. Only last_acti | ORD-053 — UrbanThread, 800 Polo shirt; status IN_PROGRESS, stage ASSEMBLY, due 2026-04-10, last recorded activity 2026-03-31. Only last_acti
- M04 (multi_turn): Due today only, or include the next seven days? Overdue active orders will be included. | Business date: 2026-04-01. Review window: 2026-04-01 through 2026-04-08 (including overdue active orders). Earlier due date first; ties: old | Business date: 2026-04-01. Review window: 2026-04-01 through 2026-04-08 (including overdue active orders). Earlier due date first; ties: old
- A01 (ambiguous): Several matching orders. Which order ID, quantity or due date? ORD-114: Hoodie, 2000 pieces, due 2026-03-23; ORD-083: Hoodie, 1000 pieces, d
- A02 (ambiguous): Which order should I draft for? Please give its ID, or choose a summary draft.
- A03 (ambiguous): Several matching orders. Which order ID, quantity or due date? ORD-073: Hoodie, 400 pieces, due 2026-04-20; ORD-008: Polo shirt, 600 pieces,
- A04 (ambiguous): Which stage: knitting, assembly, washing or packing? (and which date, if not yesterday)
- A05 (ambiguous): Does the deadline mean ready at our factory or delivered to the customer?
- A06 (ambiguous): Which order should I use? Please give its ID or customer.
- U01 (unanswerable): This system holds no prices, costs, revenue or margins: orders.csv records who ordered what, how many pieces and when. I can report counts, 
- U02 (unanswerable): The data has no worker, operator or shift records: production_log.csv holds factory-wide pieces per stage per day only. I can show the stage
- U03 (unanswerable): There is no order ORD-999 in the current records. Order IDs run ORD-001 to ORD-120; check the number or give the customer and product instea
- U04 (unanswerable): Recorded facts and labelled interpretation: {   "date": "2026-03-25",   "comparison": {     "stage": "ASSEMBLY",     "date": "2026-03-25",  
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
- Ac05 (action): Which draft should I preview? Choose a draft number. Each draft is confirmed separately.
- Ac06 (action): Draft 1 · To: planner Department: ASSEMBLY Subject: ThreadPilot chase-up | ORD-120 Please check the current status and confirm the next step | {"total_orders": 120, "by_stage": {"COMPLETE": 86, "ASSEMBLY": 10, "PACKING": 2, "WASHING": 10, "KNITTING": 12}, "by_status": {"COMPLETE": 8
