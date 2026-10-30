# Sprint 3 changes: voice input, automatic alert emails, multi-order memory, visible tool calls, the "8 same weekdays" rationale

Branch `feat/sprint3-voice-alerts-memory-tools`, 30 Oct 2026. Each item answers a question from the Sprint 2 review.

## 1. Voice input and automatic alert emails

**Voice** (`frontend/voice.js`, `backend/app/api/voice_api.py`)
- Tap ♩ and speak; the question is sent when you stop speaking, and the answer to a spoken question is read aloud (first three lines).
- The browser's own speech recognition is used where it exists (Chrome, Edge, Safari). Elsewhere the page records a short clip and
  `POST /api/v1/voice/transcribe` transcribes it with the configured speech model (`TRANSCRIBE_MODEL`, default `whisper-1`), with the
  factory's customer and product names as a hint. Audio is not stored.
- Spoken order numbers are cleaned up: "O R D zero zero five", "ord 5", "order number 120" become ORD-005, ORD-120. A bare
  "order 500" is left alone, since it may be a quantity.
- Safety: a spoken confirmation ("send now", "confirm", "save it") is never sent by voice. It is put in the box and waits for a tap.

**Automatic alert emails** (`services/alert_policy.py`, `services/alert_delivery.py`, `api/alerts_api.py`, Settings page)
- New P1 trigger, a **sudden excursion**: the latest working day below the mean minus 3.5 SD of the previous 8 same weekdays. It emails
  the same day instead of waiting for the 3-day rule; one problem still emails once (shared key with the sustained drop).
- The manager turns alert emails on in Settings ("Email me at once when something needs me today"); `ALERT_EMAILS_ENABLED` still works.
- "Send me a test alert now" in Settings; a long-running server checks every 5 minutes (CloudBase: the existing minute timer).
- The Settings card shows what would be emailed right now, what goes to the digest and what waits for the briefing.

## 2. Several orders in one chat (`services/conversation_memory.py`)

The conversation keeps the orders it discussed (first-mention order and most recent). Before the planner runs, an unambiguous
reference becomes the explicit ID: "the first one", "the second one" (after a candidate list: from that list), "the other one",
"both of them" / "compare them", "the scarf one", "the Harbor Knits one". The answer starts with "(Reading “the first one” = ORD-005,
from this conversation.)", and a `recall_conversation` step shows in the tool calls. A description matching two discussed orders is
not rewritten: the system asks. The AI workspace lists "Orders in this chat"; tapping one puts its ID in the question box.

## 3. Tool calls shown while answering

The chat stream now sends `step` events: the planner's reading (intent and details), memory, every tool call with its inputs, a
one-line result, the source rows and the time, then "Writing the answer". They appear live above the answer and stay under it as
"How I answered · N tool calls". Same tool names as `docs/TOOL_SPECIFICATION.md`.

## 4. Why "normal" is the previous 8 same weekdays (`analysis/baseline_window.py`, `docs/BASELINE_WINDOW.md`)

Measured on this factory's data with the product's own rules, for 4 to 12 weeks: 8 weeks cuts false alert emails from about 0.67 a
month (4 weeks) to about 0.1, still catches every 30% drop on its third day and 83% of 5-day 20% drops; 10–12 weeks add little and
leave few days with a full baseline in 90 days of data. The chat answers "why eight?" / "why not the last 7 days?" with these figures
(`explain_baseline_choice`), and the home screen's production chart has a short "Why eight same weekdays?" note.

## Tests

`backend/tests/test_sprint3.py` (12 tests). Offline evaluation unchanged: 88/88 questions, 116/116 turns, 0 of 2,117 numbers untraced.
