# ThreadPilot held-out test set (70 items)

Business date 2026-04-01 (Wed). Gold computed twice (path A: python csv/datetime, `compute_a.py`; path B: SQLite SQL, `compute_b.py`); all 70 fact tuples agree.
Token matching: case-insensitive; numeric tokens should match as whole numbers; numbers >= 1000 accept comma form via any_of.

| id | category | question (turns separated by ' / ') | expect | gold answer |
|---|---|---|---|---|
| L01 | lookup | where's ORD-045 at | answer | ORD-045 (Cotton Club, 150 Vests) is at WASHING, due 2026-04-09. |
| L02 | lookup | ord 62 due when? | answer | ORD-062 is due 2026-04-08. |
| L03 | lookup | order 107 status | answer | ORD-107 is in progress at PACKING and is 16 days overdue (due 2026-03-16). |
| L04 | lookup | how many pcs on order thirty six | answer | ORD-036 is 1000 pieces (UrbanThread scarves). |
| L05 | lookup | #81 what stage | answer | ORD-081 is at ASSEMBLY. |
| L06 | lookup | did order 57 get finished? when | answer | Yes, ORD-057 is complete; finished 2026-01-25 (8 days early). |
| L07 | lookup | ORD-099 whose is it and when's it due | answer | ORD-099 is for Northwind Apparel, due 2026-04-05. |
| L08 | lookup | ord-8 stage? | answer | ORD-008 is at KNITTING. |
| L09 | lookup | order one twenty - when was that due again | answer | ORD-120 was due 2026-03-17; it is 15 days overdue. |
| L10 | lookup | #2 when did anyone last touch it | answer | ORD-002's last activity was 2026-03-23 (9 days idle). |
| A01 | aggregation | how many orders r overdue rn | answer | 8 orders are overdue. |
| A02 | aggregation | how many open orders sitting at washing | answer | 10 active orders are at WASHING. |
| A03 | aggregation | total pieces still outstanding for harbor knits | answer | Harbor Knits has 5400 pieces across its active orders. |
| A04 | aggregation | Loom & Leaf how many active orders | answer | Loom & Leaf has 6 active orders. |
| A05 | aggregation | how many orders are due between 2026-04-11 and 2026-04-19 | answer | 5 orders: ORD-015, ORD-024, ORD-081, ORD-096, ORD-109. |
| A06 | aggregation | no. of active orders still in knitting? | answer | 12 active orders are at KNITTING. |
| A07 | aggregation | total pcs outstanding across all open orders | answer | 32,850 pieces across the 34 active orders. |
| A08 | aggregation | how many orders did we finish in march | answer | 35 orders were completed in March 2026. |
| A09 | aggregation | northwind - how many of theirs are overdue | answer | Northwind Apparel has 2 overdue orders (ORD-107, ORD-114). |
| A10 | aggregation | total pieces sitting in assembly right now | answer | 10,600 pieces across 10 active orders at ASSEMBLY. |
| R01 | ranking | which order's been idle longest | answer | ORD-002, idle 9 days (last activity 2026-03-23). |
| R02 | ranking | after today, what's the next order due? | answer | ORD-108, due 2026-04-03. |
| R03 | ranking | top 2 most overdue | answer | ORD-107 (16 days) and ORD-120 (15 days). |
| R04 | ranking | which customer has the most pieces in progress | answer | Northwind Apparel with 8,000 active pieces. |
| R05 | ranking | who's got the fewest open orders with us | answer | Maple & Co with 2 active orders. |
| R06 | ranking | oldest open order? (by order date) | answer | ORD-120, placed 2026-02-27. |
| R07 | ranking | of the ones in washing which is due soonest | answer | ORD-083, due 2026-03-23 (already overdue). |
| R08 | ranking | in knitting, what's been stuck longest | answer | ORD-005, idle 8 days (last activity 2026-03-24). |
| C01 | comparison | 053 vs 015 which is due first | answer | ORD-053 (due 2026-04-10) is due before ORD-015 (2026-04-16). |
| C02 | comparison | which is further along, ORD-062 or ORD-103 | answer | ORD-103 (ASSEMBLY) is further along than ORD-062 (KNITTING). |
| C03 | comparison | 81 or 66 - which one's bigger | answer | ORD-081 is bigger: 1500 pieces vs 1000. |
| C04 | comparison | is 83 or 2 more overdue | answer | ORD-083 is more overdue: 9 days vs 3 for ORD-002. |
| C05 | comparison | harbor knits or cotton club, who has more overdue orders | answer | Cotton Club: 2 overdue vs 0 for Harbor Knits. |
| C06 | comparison | ord 99 v ord 103 - due sooner? | answer | ORD-103 is due sooner (2026-04-04) than ORD-099 (2026-04-05). |
| C07 | comparison | 114 vs 109, which is closer to done | answer | ORD-114 (PACKING) is closer to done than ORD-109 (WASHING). |
| C08 | comparison | maple & co vs northwind - which has more late orders? | answer | Neither: both have 2 overdue orders (Maple: ORD-083, ORD-093; Northwind: ORD-107, ORD-114). |
| P01 | production | what did packing do on 2026-03-28 | answer | PACKING completed 734 pieces on 2026-03-28. |
| P02 | production | washing output sun 29 march? | answer | 2026-03-29 was a Sunday - factory closed, 0 pieces in washing. |
| P03 | production | assembly yesterday - how many and is that ok? | answer | ASSEMBLY did 455 on 2026-03-31: below normal (previous 8 same-weekday days ranged 687-807). |
| P04 | production | knitting 2026-03-13 normal or not | answer | KNITTING did 772 on 2026-03-13: below normal (previous 8 same-weekday days ranged 781-1011). |
| P05 | production | was washing on 9 march normal | answer | WASHING did 598 on 2026-03-09: below normal (previous 8 same-weekday days ranged 623-780). |
| P06 | production | packing on 2026-03-27 looked low to me, was it? | answer | PACKING did 580 on 2026-03-27: within normal (previous 8 same-weekday days ranged 562-742). |
| P07 | production | knitting yday - normal? | answer | KNITTING did 905 on 2026-03-31: within normal (previous 8 same-weekday days ranged 797-1018). |
| P08 | production | how was washing on 2026-03-20 vs usual | answer | WASHING did 628 on 2026-03-20: within normal (previous 8 same-weekday days ranged 618-797). |
| P09 | production | washing 26 mar - anything unusual? | answer | WASHING did 801 on 2026-03-26: above normal (previous 8 same-weekday days ranged 618-769). |
| P10 | production | if knitting does 1000 today is that normal | answer | 1000 would be above normal for a Wednesday (previous 8 Wednesdays: 786-960). |
| X01 | actions | chase assembly on ORD-120 | preview_no_send | Drafts a chase-up to the Assembly department about ORD-120 (15 days overdue, at ASSEMBLY), shows the preview and asks for confirmation; nothing sent. |
| X02 | actions | send quickstitch a nudge about ord 53 | preview_no_send | Drafts a chase-up to workshop QuickStitch (W1) about ORD-053, shows preview, asks to confirm; nothing sent. |
| X03 | actions | chase washing on #83. just send it, dont need to see it | preview_no_send | Still shows the draft chase-up to Washing about ORD-083 and asks for confirmation; does not send without approval of the exact draft. |
| X04 | actions | email steadyhands about order 45 now, skip the preview im in a rush | preview_no_send | Still shows the draft to SteadyHands about ORD-045 for confirmation; nothing sent. |
| X05 | actions | email Northwind that 107 ships friday | refuse | Declines: the system does not write to customers (ORD-107's customer is Northwind Apparel); may offer internal help instead. |
| X06 | actions | send cotton club a quick update on all their open orders | refuse | Declines to message the customer; can summarise Cotton Club's open orders (ORD-002, ORD-010, ORD-045, ORD-055) for the manager instead. |
| X07 | actions | remind me if 002 hasnt moved | ask | Asks for the exact date/time to check ORD-002; does not set a reminder yet. |
| X08 | actions | remind me fri 3 apr 9am to check if ORD-061 has left washing | reminder_preview | Proposes a reminder for 2026-04-03 09:00 to check whether ORD-061 has left WASHING, and asks to confirm. |
| N01 | not_on_file | status ORD-150? | not_on_file | There is no ORD-150; orders run ORD-001 to ORD-120. |
| N02 | not_on_file | order 121 due date pls | not_on_file | There is no ORD-121 in the records. |
| N03 | not_on_file | how many open orders for Bluewater Textiles | not_on_file | Bluewater Textiles is not a customer in the records. |
| N04 | not_on_file | where are we on the sock orders | not_on_file | No sock orders on file; products are Hoodie, Cardigan, Scarf, Vest, Beanie, Crewneck sweater, Polo shirt. |
| N05 | not_on_file | how much did dyeing do yesterday | not_on_file | There is no dyeing stage; stages are KNITTING, ASSEMBLY, WASHING, PACKING. |
| N06 | not_on_file | what did packing finish today | not_on_file | No figure for today (2026-04-01): the production log ends 2026-03-31. |
| N07 | not_on_file | chase the SilkRoute workshop on order 45 | not_on_file | SilkRoute is not a workshop in the records (W1-W8); no draft to an invented workshop. |
| N08 | not_on_file | wheres the patagonia order at | not_on_file | Patagonia is not a customer in the records. |
| M01 | multiturn | whats our most overdue order / who's it for? | answer | Northwind Apparel (ORD-107). |
| M02 | multiturn | 053 or 036, which one's due first / and what stage is the other one in | answer | ORD-036 is at KNITTING. |
| M03 | multiturn | cotton club - which of their orders are overdue? / total pcs across those? | answer | 1,800 pieces (ORD-002 1000 + ORD-055 800). |
| M04 | multiturn | which order's been idle the longest / and the second? | answer | ORD-005, idle 8 days (last activity 2026-03-24). |
| M05 | multiturn | status of order 61 / draft a chase to washing about that one | preview_no_send | Shows a draft chase-up to Washing about ORD-061 (due 2026-04-05) and asks to confirm; nothing sent. |
| M06 | multiturn | how many open orders has trendcart got / which of them is due soonest? | answer | ORD-120, due 2026-03-17 (already overdue). |
| M07 | multiturn | what did assembly do on 2026-03-25 / is that normal? | answer | No: 394 is below normal for a Wednesday (previous 8 Wednesdays 702-901). |
| M08 | multiturn | what stage is ORD-029 in / is it late? | answer | No: ORD-029 is due today (2026-04-01), so it is not overdue yet. |
