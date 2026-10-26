# CEO interface review (26 Oct 2026) and what changed

The live build was reviewed as a clothing-franchise CEO would use it: every screen on desktop (1366 px) and phone
(375 px), each given ten seconds to answer the question a CEO brings to it. Full write-up with screenshots and the
wireframe: https://claude.ai/artifact/PT5wNJissGN69y2vr6gUSs. This page records the verdict, the findings and the
fixes that landed, so the design intent survives the next refactor.

## The ten-second test (before)

| Screen | Question I bring | What I saw in 10 s (23 Oct build) | Pass |
|---|---|---|---|
| Dashboard | What needs me today? | five counters with decorative sparklines, "Analyzing…", eight AI sentences; the three decisions inside a 390-px scroll box at the bottom-right (4,273 px down on a phone) | no |
| AI workspace | A quick answer | blank chat; first answer in ~70 s as a paragraph with raw `**` marks | no |
| Orders | Which orders are in trouble? | 120 rows, 8 pages, every badge the same colour | partly |
| Risk orders | What do I expedite? | 34 rows, two text columns; the expedite review opened with a table of zeros | partly |
| Exceptions | What went wrong? | severity cards with a clear sentence each | yes |
| Historical predictions | How likely is it late? | a second risk scale (99.3 % High) under a stale-data banner | no |
| Feasibility | Can we take this order? | "Conditional" and three dates, no yes/no | no |
| Watches | What am I waiting on? | empty, plus a banner saying no scheduler is connected (untrue) | no |
| Activity log | What was sent in my name? | two receipts, clear | yes |
| Settings | Is the daily email on? | demo clock first; "Automatic briefing paused" in grey | partly |

The pattern behind every failure: the system computes a judgement, then shows the evidence instead of the judgement.

## What changed (branch `feat/ceo-home-screen`)

**Home screen** (`frontend/dashboard.js`, `dashboard.css`, `backend/app/services/home_service.py`, `GET /api/dashboard/home`)

1. A status line replaces the headline and the five counters: `Wed 1 Apr · RED · 8 overdue · Assembly −39 % for 6 days · 3 decisions need you`. Colour = RED when a P1 alert is open, AMBER for P2, GREEN otherwise, from the same `alert_policy.detect` the alert emails use. Counters become a one-line strip of links.
2. "Decide today": at most three cards, one per entity, P1 before P2, each with one button. A stage drop → "Ask the floor" (drafts the chase-up to that department through the usual preview → confirm gate); a near-due miss or an overdue order → "Review options" / "Confirm a new date" (opens the order on the Risk page with the expedite analysis); a stalled customer → "Call the customer". The rest wait behind "N more in Risk orders".
3. Order health is one stacked bar (late / at risk / on track) with the 30-day on-time rate and its change; Production pulse is four bars against the previous-eight-same-weekday band (the `check_normality` rule), with the stage below range marked `−39 % · 6 d`.
4. The morning briefing shows the first sentence of each of its three sections and the time it was written; nothing regenerates on page load ("Rewrite" does). To-dos are the manager's own items plus at most three AI next steps that name an order or a stage; "Verify / Check / Confirm" sentences are not shown, and the briefing prompt now asks for decisions in at most 20 words.
5. The chat box sits on the home page (typed or spoken) and answers in the follow-up drawer. No nested scroll regions anywhere; the floating "Ask AI" button is hidden on the home page.
6. Phone: status → decisions → ask box → the two pictures → briefing → to-dos; 3.9 screens instead of 5.3, no sideways scroll.

**Chat** (`ai-api.js`, `ai-stream.js`, `conversation.py`, `workflow_api.py`)

7. A `facts` SSE event carries the server's own answer the moment the tools finish, before the model narrates, so the first useful line lands in a second or two; the narration replaces it and the facts stay under "Facts from the records".
8. Answers render light markdown (bold IDs, numbered lists); the narrator is asked to answer ranking questions as a numbered list, one order per line. Sources collapse to "34 rows from orders · as of 09:00"; order cards fold behind "Related orders (n)" when an answer lists more than two.

**One risk vocabulary** (`app.js`, `data-views.js`, `scheduling.js`, `scheduling_api.py`)

9. Every badge says late / at risk / on track / unassessed (the shared queue level). The size-based AFT chance rides on each risk row (`forecast`) and shows as one line inside the order card ("Late-delivery chance for an order this size: 34 % · expected finish …"); for an order already past due it shows the expected finish only. The 100-point rule score is retired from the manager's screens; the imported model export (Historical predictions) leaves the manager navigation and is linked from Settings.

**Expedite review** (`scheduling.js`, `review-drafts.js`)

10. The dialog leads with the verdict ("Keep the current order", "Expedite: worth it", "Trade-off: your call", "Suspected stall: check first") and one sentence of consequence, then a before/after finish bar. An order already first in its queue says so and offers the two options left (outside workshop, new date). All labels are English.

**Smaller fixes**

11. `#/` lands on the dashboard instead of "Page not found". Orders opens with two short lists (late, at risk) and the full filtered table behind one click; activity gaps colour at 5 and 10 days. The watches banner states the server checks every minute. Settings leads with the daily briefing state (red when paused) and moves the demo clock to the bottom under "Demo".

## Still open

- Deploy: the merged release branch, including this, has to reach CloudBase for any of it to show on the live site.
- The feasibility result page keeps its three equal cards above the shared verdict; the verdict headline and the stacked capacity chart from PR #5 already lead once the shared estimate loads.
- The 07:00 briefing is still paused on the live site.

## How to check it worked

Give the home screen to someone who has never seen it, cover it after ten seconds and ask what they would do first. If the answer names an order or a stage and an action, the screen passes. Repeat on a phone. `tests/e2e/dashboard_ai_render.cjs` and `backend/tests/test_home_screen.py` keep the structure honest; the ten-second test keeps it useful.
