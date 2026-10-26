# What ThreadPilot can do for you, and what it will not do

The co-pilot is useful only if a general manager can let it near real orders without worrying. So every action follows one rule
and the limits are written down, not left for the manager to discover.

> **Preview, then confirm, then log.** Nothing that has a side effect happens before the manager presses Confirm on a card that says
> what will happen and what the worst case is. Everything that does happen is written to an activity log.

The recorded conversations that show this working are in `docs/conversation_scenarios.md` (S6 to S8). The tool-by-tool
specification is `docs/tool_spec.md`; the triggers that interrupt the manager are `docs/alert_triggers.md`.

## The actions

| Action | Ask it like | What the card shows | Worst case if the manager confirms by mistake | What stops it going wrong | What it cannot do |
| --- | --- | --- | --- | --- | --- |
| **Chase an order** | "Chase ORD-120" | The draft message, the recipient, an editable text | One unwanted message to one colleague | A confirmation key tied to that one order and that one text; it expires after 15 minutes; the order is re-read before sending and the action is refused if it changed; confirming twice does nothing the second time | Send anything by itself. With no sender configured, nothing is sent and the answer says "not sent" (in the demo it is only logged) |
| **Add a note** | "Add a note to ORD-120: waiting for the customer's trims" | The note text, editable | A wrong note in the activity log | The same confirmation gate | Change any order field. A note is a record, not an edit |
| **Watch an order or a stage** | "Tell me if ORD-120 hasn't moved by Friday" | The condition, when it will be checked | One extra alert in a later briefing | Created only after confirmation; listed under Watches and removable at any time; checked once each morning in the demo | Check continuously, or act when it fires: it only tells the manager |
| **Reminder** | "Remind me tomorrow if packing is still behind" | The condition and the day | One extra alert | Same as a watch. If the condition is no longer true the reminder clears itself instead of raising a false alarm | Send a reminder anywhere outside the system |
| **Briefing e-mail draft** | The Dashboard's briefing e-mail feature | An editable draft built from that day's saved briefing | A draft the manager did not need | The draft is stored with a version number, so two people editing do not overwrite each other. **Send with Outlook** sends only on the manager's click with the full text on screen, from their own mailbox, as plain text; a second send asks first; each send is recorded ([outlook_setup.md](outlook_setup.md)) | Send by itself, or from the chat. The server cannot send it: only the manager's browser holds the Microsoft sign-in, and only with permission to send (not read) mail |

## What it will refuse, and what it says

| If you ask it to | It answers | Why |
| --- | --- | --- |
| Cancel, delete or change an order ("Delete ORD-005") | "I can't cancel, delete or change orders. I only read the data and, after you confirm, log notes, chase-ups and watches. Nothing was changed." and points to the Memos card and the production planner | The chat reads the data; the planner owns the order |
| Give revenue, profit, prices or margins | "This system holds no prices, revenue or profit." | The data has pieces, dates and stages only |
| Name the best or worst worker | "No worker names or staffing data are held." | Output is recorded per stage per day, not per person |
| Say *why* a stage dropped | Gives the drop (e.g. "297 pieces, 59.5% below its usual 733") and says "the production log records output, not causes, so I cannot say why" | A number is evidence; a cause is a guess |
| Forecast demand beyond two weeks | "I forecast orders only for the next two weeks." | The forecast covers the next 12 working days and no further |
| Answer "is it late?" with no order in mind | Asks which order | Guessing would answer about the wrong order |
| Answer about "the TrendCart order" when there are six | Lists them and asks which | Same |
| Promise a delivery date ("Can we take 800 hoodies by the 25th?") | A date range, the bottleneck stage and the assumptions, never a plain yes | Queued orders count in full, with no overtime and no extra workshop capacity |

## Hard limits (true of the whole system)

1. **Reads only.** The dashboard chat has no write access to orders. The AI question endpoint uses a separate database account
   and refuses to start unless that account differs from the main one and holds only direct SELECT/USAGE grants.
2. **No hidden sending.** The backend sends only through a configured webhook. Without one it returns `not_sent` and never
   pretends to have succeeded; if the network result is unclear it returns `unknown` and keeps the same idempotency key so a retry
   cannot send twice.
3. **One confirmation, one action.** A confirmation applies to one order and one text. A new question or a change to the draft
   cancels the earlier preview.
4. **The data is data, not instructions.** Text inside an order or a spreadsheet cell is never treated as a command to the model.
5. **Every figure has rows behind it.** Answers carry their sources (file and line), and "Show detail" opens the rows. If the
   rows cannot support an answer, the answer says so.
6. **Estimates say they are estimates.** A projected finish or a feasibility range always carries its assumptions and is
   labelled "an estimate with assumptions, not a commitment".

## What is not covered yet

- **One workspace, one user.** There is no login, no per-person permissions and no multi-tenant separation. The backend is meant to
  run as a single Uvicorn worker; the session ID is a bearer secret and must not be shared.
- **The demo is not the live system.** The offline dashboard chat uses rules and the same tools; the live backend uses an OpenAI
  intent classifier. The recorded transcripts and the 36-question results describe the offline chat. The live backend passed
  36 of 45 turns on its first full batch (rate limits caused 7 of the 9 failures); that is all that has been measured there.
- **Real sending is untested with a real provider.** The webhook contract is specified and the send path is tested with recording
  and uncertain stand-in senders (`backend/tests/test_workflow.py`), not with a production mail or chat service.
- **The forecast is no better than repeating the last period.** It is shown as a range for planning, not as a prediction to
  commit to a customer (`docs/prediction_validation.md`).
- **The data is thin.** The sample holds about 29 working days of work in progress against 12 to 30 working days allowed, so a
  large share of orders are overdue or at risk. Findings on it show the mechanism works, not how a healthy factory behaves.
- **No real GM has used it.** The usefulness claims here are about design and checks, not measured time saved.
