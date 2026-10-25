# Business case (reconstructed from the Sprint 1 deck, backup slide 15)

These are **estimates, not measurements**: no planner has been timed and the dataset holds no prices. Every input is listed so the numbers can be challenged line by line. Figures are for one factory, one year, in SGD.

## 1. Planner time freed

Today each of the brief's five manager questions costs a planner a phone call, a wait and sometimes a wrong answer. Per factory day (likely case; each task was given a low / likely / high range and the combination drawn 10,000 times):

| Task | Minutes today | Times per day | With ThreadPilot |
|---|---|---|---|
| Morning report | 30 | 1 | 5 min |
| Order-status call-back | 10 | 3 | 1 min |
| "Can we take this order?" | 45 | 0.5 | 10 min |
| "Why did a stage drop?" | 30 | 0.5 | 5 min |
| Chase-up message | 10 | 1 | 2 min |
| Re-check a reminder | 10 | 1 | 0 min |
| Weekly KPI report (share per day) | 20 | 1 | 5 min |

Result: about 73 planner-hours a month today, 11 with ThreadPilot, so **62 hours saved (range 51–75)**. At a Singapore planner's pay plus CPF (S$48k a year → S$24.6 an hour) that is **≈ S$18.4k a year**, about a third of a person.

## 2. Lateness avoided (simulated)

The same simulated factory with the same random problems was run twice: problems noticed by a weekly check versus by the 07:00 briefing. Over about 88 orders, total lateness fell by **30.5 working days every two months (95% range 18–43, from 40 runs)**. Priced at 1% of the order value per day late (half of a published US retailer vendor rate of 2%) on an average order of US$5,515 → S$72 per order-day → **≈ S$13.1k a year**.

## 3. Running cost

OpenAI usage, Tencent CloudBase hosting and upkeep: **≈ S$1.9k a year**.

## 4. Net value and the alternative

| A year, likely case | SGD |
|---|---|
| Planner time freed | +18.4k |
| Late penalties avoided | +13.1k |
| Running ThreadPilot | −1.9k |
| **Net value** | **≈ 29.6k** |

Hiring a full-time assistant to give the same on-call answers would cost about S$49.1k a year.

## What would make this a measurement

1. Time one planner for a week on the seven tasks above (replaces the assumed minutes).
2. Use the factory's real late-penalty terms (replaces the 1%/day assumption).
3. Compare the simulator's 30.5-day figure against real lateness once the alert policy and briefing have run live for two months (`docs/ALERT_POLICY.md`, `evaluation/`).

Source: Sprint 1 presentation backup slide 15 and its speaker notes; the simulator that produced the lateness figure lives in the `footoonming/DSS5105_Track1` repository (`simulation/`).
