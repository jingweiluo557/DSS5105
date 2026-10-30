# Alert policy — when ThreadPilot interrupts the general manager

Code: `backend/app/services/alert_policy.py` (detection + gating, pure Python), `alert_delivery.py` (ledger + Outlook send, flagged), `api/alerts_api.py`. Tests: `backend/tests/test_alert_policy.py`. Default: **dry run** (`ALERT_EMAILS_ENABLED=false`): every decision is recorded and visible at `GET /api/alerts/preview`, nothing is sent.

## The philosophy (why so few emails)

The brief says it: "a co-pilot that pings ten times a day gets muted". Industrial alarm management (ISA-18.2 / EEMUA 191) and on-call practice (SRE) agree on the same rules, so we borrowed them:

1. **An interruption is earned, not default.** An email goes out only when something (a) needs a decision or action from the GM *today*, (b) the system cannot handle on its own, and (c) is new or materially worse than what was already reported. Everything else waits for the 07:00 briefing, which is the one scheduled touch per day.
2. **Three tiers, three channels.**

| Tier | Meaning | Channel | Cooldown |
|---|---|---|---|
| P1 — act now | a decision today changes the outcome | one email at once, at most 3 a day | 24 h |
| P2 — decide today | should be looked at in the morning or after lunch | batched into the 07:00 briefing or a 14:00 digest, only when non-empty | 72 h |
| P3 — watch | worth knowing, no action yet | briefing and the app only, never email | 7 d |

3. **Never nag.** Each alert has a dedupe key (`kind:entity`). The same key is not emailed again within its cooldown, and after the cooldown an *unresolved* item is reminded inside the digest, never by a fresh email. It is emailed again only if it got worse (score up by 8 or more).
4. **Caps and quiet hours.** At most 3 immediate emails per day; the overflow goes to the next digest as "several critical items". 22:00–06:00 holds P2/P3; P1 passes.
5. **Shelving.** The GM can mute a key ("ORD-107 overdue") or a kind ("overdue") for N days; shelved alerts stay visible in the app with the mute shown.
6. **Clearing is silent.** When a condition clears, nothing is emailed; the briefing says "cleared".
7. **Measured.** `GET /api/alerts/kpis`: immediate emails per week (target ≤ 5), items per digest, and the GM's own useful / not-useful ratings (target ≥ 70 % useful). If the ratings fall, thresholds move, not the GM's patience.

## Triggers (all computed from the same snapshot the chat tools use)

| Tier | Trigger | Rule | Why it earns the tier |
|---|---|---|---|
| P1 | Sudden excursion (Sprint 3) | the latest working day below the mean minus 3.5 SD of the previous 8 same weekdays (at least 5) and below their minimum | a machine down or a stoppage should not wait three days; measured at about 0.47 false alerts a month over four stages, a one-day 40% drop caught the same day 94% of the time (`docs/BASELINE_WINDOW.md`). Shares the stage's key with the sustained drop, so one problem emails once |
| P1 | Sustained stage drop | 3 consecutive working days below the previous-8-same-weekday minimum | one low day is noise (P3); three is a line stopped or a machine down, and every near-due order behind it slips |
| P1 | Customer stalled | every active order of a customer idle ≥ 5 working days while later-due orders at the same stage moved | the queue does not explain it; a hold, material or payment issue needs a phone call |
| P1 | Will miss, no plan | due within 2 working days, best-case queue finish after the due date, no manager-approved priority | the only three options (expedite, outsource, new date) all need the GM today |
| P1 | A watch the GM set fires | existing reminder service | they asked |
| P2 | Newly overdue | IN_PROGRESS and due before the business date | the customer needs a date; not an emergency if it was already known |
| P2 | Newly high risk | shared queue risk level `high` | review in the morning with the expedite analysis |
| P2 | New large or rush order | ordered yesterday and ≥ 1500 pieces or ≤ 12-day lead | check feasibility before the planner commits |
| P3 | One low day | below the same-weekday range once | watch; the rule explicitly says one day proves nothing |
| P3 | Idle order | no activity ≥ 5 calendar days, not near due | ask tomorrow if still quiet |
| P3 | Medium risk | queue level `medium` | briefing only |

On the seed snapshot (business date 2026-04-01) the policy produces: 3 P1 (assembly below range since 28 March; ORD-029 and ORD-108 will miss), 31 P2 (8 overdue, 23 high-risk), 0 P3 (every idle order is already covered). First tick: one P1 email with three lines; the P2 items go into the 07:00 briefing grouped by kind ("Overdue: 8 — top three — and 5 more in the app"). Second tick an hour later: 34 suppressed, 0 emails. Next day with nothing changed: 0 emails, the open P1s reminded in the digest.

## What a P1 email looks like

```
Subject: [ThreadPilot P1] 3 items need you: Assembly has been below its normal range for 3 working days (44% under)

Hello Jingwei,

- Assembly has been below its normal range for 3 working days (44% under). Ask the floor what changed; check which near-due orders sit at or after this stage.
- ORD-029 (Northwind Apparel, 1500 Beanie) due 2026-04-01 will miss even in the best case. Decide today: expedite (review the queue impact), outsource, or tell the customer a new date.
- ORD-108 (Harbor Knits, 2000 Scarf) due 2026-04-03 will miss even in the best case. Decide today: ...

Details
P1 Assembly has been below its normal range for 3 working days (44% under)
  2026-03-28: 445 vs min 687 (mean 797.4); 2026-03-30: 396 vs min 720 (mean 760.9); 2026-03-31: 455 vs min 687 (mean 745.2)
  Rule: 3 consecutive working days below the previous-8-same-weekday minimum
...
Why you got this: P1: needs a decision today and is new or escalated.
Mute: reply "mute <kind> 7d" or use Settings > Alerts. Nothing in this email was sent to anyone else.
```

Three lines first, numbers and the rule underneath, the reason it was sent, and how to mute it. Every number comes from the snapshot; the model is not involved in alerts at all.

## Expedite action emails to the production team

Through the chase flow: a chase-up can be addressed to a department (`KNITTING`/`ASSEMBLY`/`WASHING`/`PACKING` emails in Settings), previewed, confirmed and sent through Outlook, with the result in the Activity Log. Since 26 Oct an applied expedite review (`POST /api/scheduling/reviews/{id}/decision` with `apply`) also returns a `dispatch_notice` — the order, its new position, the manager's reason and the orders it pushes back — and the UI offers to draft it to the order's current department through that same chat path (preview → confirm → Outlook → Activity Log). No automatic send: a wrong dispatch email to the floor is exactly the blast radius the confirmation gate exists for.

## Turning it on

1. Outlook connected in Settings, manager email set.
2. Either the manager ticks **"Email me at once when something needs me today"** in Settings (stored with the email preferences,
   manager key required, Outlook must be connected) or the deployment sets `ALERT_EMAILS_ENABLED=true`. Either one turns sending on.
3. Who runs the check: on CloudBase the minute timer (`/api/internal/email/run`) already calls the alert tick; a long-running
   server with `EMAIL_SCHEDULER_ENABLED=true` runs it every 5 minutes (`alert_loop` in `alert_delivery.py`). Caps, cooldowns
   and quiet hours apply on every tick, so running more often never sends more.
4. **Send me a test alert now** in Settings (`POST /api/alerts/test`, manager key, `X-Confirm-Write: true`) emails the manager
   the message the policy would send right now, marked [Test]. It is not recorded in the ledger, so it never uses up the
   daily cap or a cooldown.
5. Watch `GET /api/alerts/kpis` for a week; tune thresholds in `alert_policy.py` (all constants at the top) before widening.
