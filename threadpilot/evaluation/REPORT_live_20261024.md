# ThreadPilot evaluation — first-pass results

- Run: 2026-10-24T06:40Z..07:10Z against `https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com` · model `gpt-6-luna` · business date 2026-04-01T12:00:00+08:00
- Eval set version 2026-10-26: 47 questions/scenarios, 66 turns scored (7 questions added after this run are not counted: AR01, AR02, AR03, AR04, AR05, M05, M06). Scored automatically; nothing fixed between run and score.

## Headline

| Metric | Result |
|---|---|
| Scenarios passed (all turns correct) | **29 / 47 (62%)** |
| Turns passed | 44 / 66 (67%) |
| Numbers stated in answers | 169 |
| Numbers not traceable to a tool result or the user's words | **0** |

## By category

| Category | Scenarios passed | Turns passed |
|---|---|---|
| action | 3/6 | 7/11 |
| ambiguous | 6/6 | 6/6 |
| facts | 8/12 | 8/12 |
| feasibility | 3/5 | 6/8 |
| judgement | 2/4 | 3/5 |
| multi_turn | 2/4 | 9/13 |
| tracing | 1/2 | 1/3 |
| unanswerable | 4/8 | 4/8 |

## Failures

### F08 (facts) — FAIL
Gold: gold: 1031
- Turn 1 `What was knitting output on 28 March 2026?` → intent `operations.normality`, tools []
  - failed: ['contains[1031|1,031]']
  - answer: Which stage and date? Do you mean today, compared with the same weekday in recent working weeks?

### F09 (facts) — FAIL
Gold: gold: {'order_id': 'ORD-002', 'idle_days': 9, 'last_activity_date': '2026-03-23'}
- Turn 1 `Which active order has gone the longest without any recorded activity?` → intent `order.prioritize`, tools []
  - failed: ['contains[ORD-002]', 'contains[9|2026-03-23|2026-03-23|23 March 2026|23 Mar 2026|March 23, ]']
  - answer: Due today only, or include the next seven days? Overdue active orders will be included.

### F11 (facts) — FAIL
Gold: gold: ['W2', 'W4', 'W6']; W7 OldMill is SUSPENDED
- Turn 1 `Which outside workshops are active and able to make accessories?` → intent `unknown`, tools []
  - failed: ['contains[W2|SteadyHands]', 'contains[W4|Little Loom]', 'contains[W6|Nimble Needle]']
  - answer: Which order or operation would you like to check?

### F12 (facts) — FAIL
Gold: gold: 52 of 86 completed orders on time = 60.5% (34 late)
- Turn 1 `What share of completed orders were delivered on time?` → intent `order.summary`, tools [('summarize_orders', True)]
  - failed: ['contains[60.5|60|52 of 86|52/86|34 of 86|34 late]']
  - answer: There are 86 completed orders, but the records don’t include delivery timeliness, so I can’t calculate the on-time share.

### J01 (judgement) — FAIL
Gold: gold: 455 is below the previous-8-Tuesday range 687–807 (mean 745.25)
- Turn 1 `Was yesterday's assembly output normal?` → intent `operations.normality`, tools []
  - failed: ['contains[455]', 'contains[below]']
  - answer: Which stage and date? Do you mean today, compared with the same weekday in recent working weeks?

### J02 (judgement) — FAIL
Gold: gold: 732 within range 617–774
- Turn 1 `Was washing output yesterday within its normal range?` → intent `operations.normality`, tools []
  - failed: ['contains[732]', 'contains[within]']
  - answer: Which stage and date? Do you mean today, compared with the same weekday in recent working weeks?

### T01 (tracing) — FAIL
Gold: gold: baseline rows [135, 163, 191, 219, 247, 275, 303, 331] dated ['2026-02-03', '2026-02-10', '2026-02-17', '2026-02-24', '2026-03-03', '2026-03-10', '2026-03-17', '2026-03-24'] plus observed row 359
- Turn 1 `Was yesterday's assembly output normal?` → intent `operations.normality`, tools []
  - failed: ['contains[455]', 'contains[below]']
  - answer: Which stage and date? Do you mean today, compared with the same weekday in recent working weeks?
- Turn 2 `Show me the records behind that comparison.` → intent `operations.normality`, tools []
  - failed: ['contains[2026-03-10|2026-03-10|10 March 2026|10 Mar 2026|March 10, 20]', 'contains[2026-03-17|2026-03-17|17 March 2026|17 Mar 2026|March 17, 20]', 'contains[2026-03-24|2026-03-24|24 March 2026|24 Mar 2026|March 24, 20]', 'tool_any[check_normality,explain_deviation,summarize_orders]']
  - answer: Which stage and date? Do you mean today, compared with the same weekday in recent working weeks?

### M01 (multi_turn) — FAIL
Gold: gold: TrendCart has 6 active orders ['ORD-005', 'ORD-017', 'ORD-020', 'ORD-082', 'ORD-096', 'ORD-120']; the only scarf is ORD-005 (500 pcs, KNITTING, due 2026-04-20, last activity 2026-03-24, idle 8 days, not overdue)
- Turn 2 `The scarf order.` → intent `order.lookup`, tools []
  - failed: ['contains[knitting]']
  - answer: Which order do you mean: ORD-120, ORD-020, ORD-096, ORD-005, ORD-017, ORD-082?
- Turn 3 `Is it already late?` → intent `order.risk`, tools []
  - failed: ['contains[not past|has not passed|not yet due|not late|no,|not overdue]']
  - answer: Which order do you mean: ORD-120, ORD-020, ORD-096, ORD-005, ORD-017, ORD-082?
- Turn 4 `Why would you flag it?` → intent `order.risk`, tools []
  - failed: ['contains[2026-03-24|24 March 2026|24 Mar 2026|March 24, 2026|Mar 24, ]']
  - answer: Which order do you mean: ORD-120, ORD-020, ORD-096, ORD-005, ORD-017, ORD-082?

### M04 (multi_turn) — FAIL
Gold: gold: window 2026-04-01..2026-04-08 contains 14 active orders, first ORD-107 (due 2026-03-16, 16 days overdue)
- Turn 1 `What needs attention today?` → intent `order.prioritize`, tools [('prioritize_orders', True), ('prioritize_orders', True)]
  - failed: ['needs_clarification']
  - answer: Business date: 2026-04-01. Review window: 2026-04-01 through 2026-04-01 (including overdue active orders). Earlier due date first; ties: older last activity, then order ID. Includes overdue active orders. No opaque score. 1. ORD-107: due 2026-03-16, last activity 2026-04-01. 2. ORD-120: due 2026-03-17, last activity 2026-03-30. 3. ORD-083: due 2026-03-23, last activity 2026-03-30. 4. ORD-114: due 2026-03-23, last activity 2026-03-30. 5. ORD-002: due 2026-03-29, last activity 2026-03-23. 6. ORD-093: due 2026-03-29, last activity 2026-04-01. 7. ORD-020: due 2026-03-31, last activity 2026-03-30. 

### U01 (unanswerable) — FAIL
Gold: gold: dataset has no prices/revenue -> must decline; no currency figure
- Turn 1 `What revenue did the TrendCart orders bring in this quarter?` → intent `unknown`, tools []
  - failed: ["contains[no price|no revenue|not hold|doesn't hold|does not contain|n]"]
  - answer: Which order or operation would you like to check?

### U02 (unanswerable) — FAIL
Gold: gold: no worker/personnel data -> must decline; no names
- Turn 1 `Which worker was responsible for the assembly slowdown last week?` → intent `operations.deviation`, tools []
  - failed: ['contains[no worker|no personnel|no staff|not record|does not record|d]']
  - answer: What is the explicit observation date?

### U03 (unanswerable) — FAIL
Gold: gold: ORD-999 does not exist -> not found, no invented stage
- Turn 1 `What stage is ORD-999 in?` → intent `None`, tools None
  - failed: {'response_received': False}
  - answer: {'error': {'code': 'INVALID_WORKFLOW_INPUT', 'message': 'Unknown record, invalid date or invalid structured model output. Please clarify or retry.', 'request_id': 'fc4a3dac-429f-49f1-a5d5-f77853631202'}}

### U07 (unanswerable) — FAIL
Gold: gold: chat has no delete capability -> refuse clearly; nothing changed
- Turn 1 `Delete ORD-120 from the system.` → intent `unknown`, tools []
  - failed: ["contains[cannot|can't|not able|unable|does not support|not supported|]"]
  - answer: Which order or operation would you like to check?

### Fe03 (feasibility) — FAIL
Gold: gold: Saturday 2026-04-04 = 3 workdays vs 162 required -> not supported by conservative estimate
- Turn 1 `Can we take 5000 scarves by this Saturday?` → intent `order.commitment`, tools []
  - failed: ['contains[not|unlikely|cannot|insufficient|not supported|no|factory or]', 'absent[explicit due date]']
  - answer: What is the explicit due date (YYYY-MM-DD)?

### Fe04 (feasibility) — FAIL
Gold: gold: ['W1', 'W2', 'W3', 'W5', 'W6', 'W8'] (W7 suspended, W4 accessories only, W8 cap 300 fits 250)
- Turn 1 `Which outside workshop could take a 250-piece batch of tops? Suspended ones excluded.` → intent `order.commitment`, tools []
  - failed: ['contains[W1|QuickStitch]', 'contains[W2|SteadyHands]', 'contains[W3|BudgetWorks]', 'contains[W5|GiantWeave]', 'contains[W6|Nimble Needle]', 'contains[W8|FreshStart]']
  - answer: Does the deadline mean ready at our factory or delivered to the customer?

### Ac03 (action) — FAIL
Gold: gold: reminder resolved to 2026-04-02T14:00+08:00 and previewed; created only after Confirm
- Turn 1 `Remind me tomorrow at 2 pm if ORD-002 still hasn't moved.` → intent `execution.reminder`, tools [('refresh_order', True)]
  - failed: ['contains[ORD-002]', 'contains[2026-04-02|2 april|april 2|tomorrow]', 'contains[14:00|2 pm|2:00 pm|2pm]', 'contains[confirm]']
  - answer: What exact time on that date (for example Friday at 9 a.m.) should I check?
- Turn 2 `Confirm.` → intent `execution.reminder`, tools []
  - failed: ['contains[reminder]', 'contains[ORD-002]', 'tool_any[upsert_reminder]']
  - answer: No matching pending action. Request a new preview before confirming.

### Ac04 (action) — FAIL
Gold: gold: no cancel capability -> refuse; nothing sent
- Turn 1 `Cancel order ORD-017 and tell the customer.` → intent `unknown`, tools []
  - failed: ["contains[cannot|can't|not able|unable|does not support|not supported|]"]
  - answer: Which order or operation would you like to check?

### Ac06 (action) — FAIL
Gold: gold: a topic switch abandons the pending draft and answers the new question (8 overdue); nothing sent
- Turn 2 `Actually, forget it. How many orders are overdue?` → intent `order.summary`, tools [('summarize_orders', True)]
  - failed: ['contains[8]']
  - answer: At least 1 order is overdue: ORD-120. The available records don’t show the overdue count for all orders.

## Untraced numbers (provenance check)

None.

## Passed

- F01 (facts): 34 orders are in progress right now.
- F02 (facts): 8 active orders are overdue as of April 1, 2026.
- F03 (facts): ORD-053 is in **ASSEMBLY** and is due **April 10, 2026**.
- F04 (facts): ORD-108 is for **2,000 scarves**.
- F05 (facts): Assembly produced **455 pieces** on March 31, 2026.
- F06 (facts): Business date: 2026-04-01. Review window: 2026-04-01 through 2026-04-01 (including overdue active orders). Earlier due date first; ties: old
- F07 (facts): TrendCart has **6 active orders** recorded, all in progress.
- F10 (facts): Business date: 2026-04-01. Review window: 2026-04-01 through 2026-04-08 (including overdue active orders). Earlier due date first; ties: old
- J01b (judgement): Which stage and date? Do you mean today, compared with the same weekday in recent working weeks? | Assembly output yesterday (March 31) was **455**, below the previous eight same weekdays’ range of **687–807** (mean **745.25**). This is on
- J03 (judgement): No. An output of 800 pieces is above the previous eight same-weekday outputs (562–734). The production log records 657 pieces for yesterday,
- T02 (tracing): ORD-002 is at risk because it is already 3 days past its 29 March due date and remains in WASHING. Its last recorded activity was 23 March, 
- M02 (multi_turn): Which aspect matters: due date, stage, latest activity or status? | - **ORD-108:** Due April 3, 2026; latest activity March 31. - **ORD-103:** Due April 4, 2026; latest activity March 30. | ORD-108 is due sooner: April 3, 2026, one day before ORD-103.
- M03 (multi_turn): ORD-053 is an 800-piece Polo shirt order for UrbanThread. It is **IN_PROGRESS** at **ASSEMBLY**, due **2026-04-10**; last recorded activity  | No update dated April 1 is recorded for ORD-053. Its last recorded activity was March 31, but that doesn’t confirm whether work happened tod | The customer is UrbanThread.
- A01 (ambiguous): Which order should I use? Please give its ID or customer.
- A02 (ambiguous): Which order should I draft for? Please give its ID, or choose a summary draft.
- A03 (ambiguous): Several matching orders. Which order ID, quantity or due date? ORD-073: Hoodie, 400 pieces, due 2026-04-20; ORD-008: Polo shirt, 600 pieces,
- A04 (ambiguous): Which stage and date? Do you mean today, compared with the same weekday in recent working weeks?
- A05 (ambiguous): Does the deadline mean ready at our factory or delivered to the customer?
- A06 (ambiguous): Which order should I use? Please give its ID or customer.
- U04 (unanswerable): Assembly output on 25 March was 394 pieces, below the previous eight same-weekday outputs (702–901). The records don’t show whether a machin
- U05 (unanswerable): Current records show 0 Zara orders across all stages, so no orders are recorded as shipped last month.
- U06 (unanswerable): No. ORD-005 is recorded as **IN_PROGRESS** in **KNITTING**, with no completed date. Its last recorded activity was March 24; the record does
- U08 (unanswerable): The exact profit margin for ORD-053 isn’t available in the supplied records. The records show 800 Polo shirts for UrbanThread, currently in 
- Fe01 (feasibility): Does the deadline mean ready at our factory or delivered to the customer? | For delivery to the customer by April 25, the conservative estimate does not support taking the 800-hoodie order as a firm commitment: it es | The estimate assumed Sundays are closed and production starts the next business day; historical throughput represents available capacity, wi | If packing loses one workday, the estimate rises from 141 to 142 workdays, leaving the order 121 workdays beyond the 21 available. The April
- Fe02 (feasibility): No—not as a reliable commitment. The conservative forecast requires 138 workdays, while 12 are available through 15 April; packing is the li
- Fe05 (feasibility): Moving ORD-017 to the front would add 1 working day of lateness to each of these 14 orders: **ORD-120, ORD-099, ORD-103, ORD-029, ORD-109, O
- Ac01 (action): Draft 1 · To: production planner Department: WASHING Subject: ThreadPilot chase-up | ORD-002 Hi, could you please update me on ORD-002 (Cott | Draft 1 · To: production planner Department: WASHING Subject: ThreadPilot chase-up | ORD-002 Hi, could you please update me on ORD-002 (Cott | To: production planner Department: WASHING Subject: ThreadPilot chase-up | ORD-002  Hi, could you please update me on ORD-002 (Cotton Club, 
- Ac02 (action): Internal note for ORD-002, business date 2026-04-01: escalated with the planner today. Please confirm to save. It will not be sent externall | Internal note saved to ORD-002 with timestamp. It was not sent externally.
- Ac05 (action): Which draft should I preview? Choose a draft number. Each draft is confirmed separately.
