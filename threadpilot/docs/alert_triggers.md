# Alert triggers

When does ThreadPilot tell the general manager something without being asked, and when does it wait to be asked?
This page is the complete list. Every number below is a constant in `simulation/briefing.py` (the briefing and the dashboard)
or in `backend/app/` (the reminders), and `tests/test_alert_triggers_doc.py` fails if this page and the code disagree.

## The principle: one calm interruption a day, not a stream

A GM who is pinged all day stops reading. So the default is **one briefing each morning at 07:00** with at most five findings,
ranked, each with the rows behind it. The only things that can reach the GM *between* briefings are the ones the GM asked for
(a watch or a reminder) and a stage that has missed its own target three days running.

| | What | When | How the GM sees it |
| --- | --- | --- | --- |
| **Waits for the briefing** | The 8 kinds of finding below | Once a day, 07:00 (data up to the last working day) | The Morning Briefing page and its three-line summary; the same list through the chat |
| **Fires on its own: asked for** | A *watch* ("tell me if ORD-120 hasn't moved by Friday") or a *reminder* ("remind me tomorrow if packing is still behind") | Checked in the briefing of the day the GM named (demo), or every 30 seconds against the due time (backend) | A toast and a line in the chat; a log entry. Nothing is sent outside the system. |
| **Fires on its own: a setting** | A stage that missed its target for 3 working days in a row | Shown with the briefing | A red "below its target N days running" pill on the stage chart |
| **Never fires** | Anything that would need a price, a person, or a cause the data does not hold | - | The chat says what is missing instead (`docs/actions_and_limits.md`) |

## What counts as "normal"

Every stage alert compares yesterday with the **previous 8 same weekdays** (Sundays are closed): the band is the mean
&plusmn; the larger of 1.5 standard deviations and 5% of the mean, and at least 3 samples are needed. The briefing, the chat and
`dashboard_service.py` use this one definition, and a test holds them to the same numbers.

**Describing is not interrupting.** The band answers "is this a usual day?" when the manager asks. It is deliberately wide: with
real day-to-day noise of about 8 to 9%, an output below it happens on about 1 stage-day in 9, which would be about 12 interruptions a
month for the whole factory. So a stage only becomes a *finding* (something the briefing raises without being asked) when it passes a
statistical process control rule on the same baseline: below **mean - 3 SD** (a sudden drop), or a lower **CUSUM** of the daily
z-scores past its limit (a sustained smaller drop). Measured on noise resampled from the real log, that cuts false alarms from about 12
to about 2 a month while still catching every drop of 30% or more that lasts 3 days, on average within the first day. Small one-day dips
(10 to 20%) are mostly not raised, by design. The study, its tables and its limits: [spc_detection.md](spc_detection.md).

## The constants

| Constant | Value | Meaning |
| --- | --- | --- |
| `BASELINE_WEEKS` | 8 | How many previous same weekdays make up "normal" |
| `MIN_SAMPLES` | 3 | Fewer samples than this and the stage is not judged |
| `BAND_SD` | 1.5 | Band width in standard deviations |
| `BAND_MIN_PCT` | 0.05 | Band is never narrower than 5% of the mean |
| `SPC_SIGMA` | 3.0 | A stage becomes a finding when yesterday is below mean minus this many SDs (Shewhart 3-sigma) |
| `CUSUM_K` | 0.5 | CUSUM slack, in SDs: daily shortfalls smaller than this do not accumulate |
| `CUSUM_H` | 4.0 | CUSUM limit: a stage also becomes a finding when the accumulated shortfall passes this |
| `IDLE_ALERT` | 5 | Working days without activity before an order counts as quiet |
| `DUE_SOON` | 7 | Days to the due date that count as "due this week" |
| `TOP_N` | 5 | Findings shown on the page; the rest are counted ("+N more") |

## The 8 kinds of finding

Each finding has a score; the *score reason* is the formula, printed on the page next to the score. A finding is raised only
when its trigger is true on that morning.

| Finding | Trigger | Score reason (printed on the page) | Suggested next step |
| --- | --- | --- | --- |
| `stage_below_normal` | A stage's output yesterday is below its 3-sigma lower limit, or a lower CUSUM of its recent daily z-scores passes its limit (a sustained shortfall). The 1.5 SD band only describes the usual range; it no longer raises a finding on its own ([why](spc_detection.md)) | 40 + percentage below the same-weekday mean (max 40) | Check with the stage supervisor |
| `customer_stalled` | A customer has 2+ active orders, every one idle for 3+ working days, and all but at most one of them have later-due orders moving past them at the same stage (so the queue does not explain it) | 70 + 2 per stalled order | Call the customer's account manager |
| `quiet_order` | 1 or 2 orders idle for 5+ working days, due within 21 days or already past due, while later-due orders moved past them at the same stage | 45 + 3 per idle working day (max 30) | Chase the order |
| `quiet_orders` | The same, with 3 or more orders: rolled into one finding so it cannot flood the page | 55 + 5 per quiet order (max 85) | Chase the quiet orders |
| `overdue` | Any active order past its due date: always one finding, never one per order | 50 + 4 per overdue order (max 90) | Ask the planner for revised ship dates |
| `due_soon_at_risk` | An order due within 0 to 7 days that the queue model rates high or medium risk of missing its date | 55 + 3 per order | Warn the customers or add capacity |
| `wip_pileup` | More than 6 days of work queued in front of one stage | 35 + days of queued work (max 25) | Consider overtime or moving work to a workshop |
| `new_order_decision` | An order placed yesterday that is large (1,000+ pieces) or short-lead (14 days or less) | fixed 50 for large (>=1,000) or short-lead (<=14 days) orders | Run a feasibility check before confirming |

Customers already in a `customer_stalled` finding are left out of `quiet_order(s)`, so one cause is not reported twice.

## Ranking: new things rise, old things fade, worse things come back

The page is sorted by `rank_score`, not by the raw score.

- **+10** if the finding is new since the previous briefing.
- **-4 for every extra morning** it has already been reported, up to **-20**, so a problem that has not changed does not lead
  the page for ever.
- No fade at all if the score got **8 or more points worse** than the day before ("getting worse"). Small drifts do not count.
- The first briefing has no history, so nothing is "new" and nothing fades.

The official wording, shipped in every briefing file as `definitions.ranking`:

> score (see score_reason) +10 if new since the previous briefing, -4 per extra morning already reported (max -20) unless it got worse; top 5 shown, rest counted

Each finding also says *why* it is where it is: `new since yesterday (+10)`, `getting worse (no fade)`,
`open N mornings (-X)` or `first briefing`.

## Severity

A severity word is derived from the rank score so the page can be scanned: **critical** at 80 or above, **high** at 65 or above,
otherwise **watch**. The word changes the colour and label, never whether the finding is shown.

## Watches and reminders (the GM's own triggers)

| Kind | Example | Fires when | Cleared when |
| --- | --- | --- | --- |
| `no_move` | "Tell me if ORD-120 hasn't moved by Friday" | On the named day, the order has had no activity since the day the watch was made | The order moved, or it finished |
| `stage_behind` | "Remind me tomorrow if packing is still behind" | On the named day, that stage's output is below its normal band | The stage is back within its band |
| `plain` | "Remind me on Friday to call the planner" | Always, on the named day | - |

Rules that apply to all three:

- **Confirm first.** A watch is a standing instruction, so it is created only after the GM presses Confirm on a card that shows
  the condition, when it will be checked, and the worst case (one extra alert in a later briefing).
- **Checked once each morning in the demo**, with the same data as that morning's briefing, not continuously. A watch that is
  due is evaluated once and then marked fired or cleared.
- **Rewinding the date un-fires it.** In the demo, moving the date back to the day the watch was made, or earlier, resets it to
  active, because the check "has not happened yet".
- **The result is logged** in the activity log either way, including "cleared", so a quiet outcome is also visible.

### Backend reminders (scenario 3.3)

The FastAPI backend evaluates confirmed reminders itself (`monitor_loop` in `backend/app/workflow_api.py`): every **30 seconds** it
re-reads the order and checks every reminder whose deadline has passed.

| Condition | Satisfied when |
| --- | --- |
| `no_reply` | A reply from the supplier was recorded between the reminder being made and its deadline |
| `no_activity` | The order's last activity date moved after the reminder was made and no later than its deadline |

If the condition is **unmet**, one in-app notification is stored (`condition unmet at <deadline>; based on recorded data only`),
once only, and the GM reads it from `GET /api/v1/workflow/notifications/{session_id}`. If it is **met**, nothing is stored. If the
data source is unavailable the check is kept for the next round instead of being marked done. **No email, SMS or chat message is
sent by this loop.**

## What deliberately does not alert

- **Single late orders one by one.** Overdue orders are one finding with the three worst named; the full list is one question away.
- **A stage that is only slightly below its average.** Inside the band is normal; the band exists so ordinary day-to-day
  variation is not an alert.
- **Anything the data cannot support.** No alert is based on revenue, people or causes; the log records output, not reasons.
- **The same unchanged problem at the top of the page every day.** It fades by 4 points a morning until it gets worse.
- **Sundays.** The factory is closed, so no output is expected and none is judged.

## Limits, said plainly

- The demo's watches are checked once per morning, not in real time; only the backend's reminders run on a 30-second loop.
- The thresholds (5 idle days, 7 days to due, 6 days of queued work, the +10/-4 ranking) are design choices made for this data
  set, not values fitted to a customer's tolerance. They are constants in one place so they can be changed without touching the logic, and nothing has
  yet been tuned with a real GM.
- On the shipped 15 mornings the briefing found 101 findings, showed 74 and counted the other 27 (never more than 5 shown, between
  4 and 9 found each morning). That is a property of this synthetic data, not a measured alert rate for a real factory.
- Discovery was checked against events planted in the simulator (5 of 5 found, 1 to 4 days after each started;
  `simulation/evaluate_discovery.py`, results in the README). It has not been checked against events a real factory would not label.
