"""Spoken lines for the two teleprompter videos (demo/make_prompter.py).

The burned-in captions are written to be read, and many run at 200-570 words a minute: too fast to say. These are the
lines to SAY, each anchored to the caption(s) on screen at that moment (cue indexes into the video's .srt) and short
enough to speak at about 145 words a minute inside that window. Edit freely; make_prompter.py warns when a line no
longer fits its window.

Each entry: (first_cue, last_cue, speaker, text). The line starts when first_cue appears and must be finished when
last_cue ends.
"""
W, M, K = 'Le Wenni (Wendy)', 'Foo Toon Ming (Matthew)', 'Kevin Royce Thomson'
P = 'The AI agent speaks (stay silent until it finishes)'

# ThreadPilot_Demo.mp4 (the full product demo with the phone and voice chapter, 4:24) — cues from ThreadPilot_Demo.srt
# The presenter's lines below ARE the video's subtitles (assemble_demo.py --spoken-subs): what is on screen is what is said.
# In the phone chapter two voices are already in the recording and get no voice-over: the manager speaking each question
# into the phone (LIVE below) and the AI agent answering aloud (speaker P). The presenter speaks only in the gaps.
LIVE = {11: 'Where is O R D zero zero five?', 15: 'Which customer has the most pieces in progress?', 17: 'Chase washing on O R D zero eight three.', 19: 'Send now.'}

DEMO = [
    (0, 0, W, 'ThreadPilot, the general manager’s co-pilot: one working day at a knitwear factory, on its own records.'),
    (1, 1, W, 'Before she is at her desk, it emails her unasked, in the daytime only. This is the email, word for word.'),
    (2, 2, W, 'When is it due? The system works it out: seven o’clock, three urgent items. We jump to two seconds before.'),
    (3, 3, W, 'Seven o’clock: the check fires. One email to the manager, three urgent items, never sent twice. In this replay it is recorded, not delivered.'),
    (4, 4, W, 'She opens the app. The day is on one screen: red, 8 overdue, assembly below normal for 6 days, 3 decisions.'),
    (5, 5, W, 'Each decision has one button. Review options simulates the queue for order 29.'),
    (6, 6, W, 'Moving order 29 up saves 5 days but adds 11 to six other orders, so it says: keep the order.'),
    (7, 7, W, 'Drafted before she asks: chase-ups for the two stalled orders, written from the records.'),
    (8, 8, W, 'Review and send opens the preview. She reads it and confirms.'),
    (9, 9, W, 'Sent and logged. Nothing went out before her click.'),
    (10, 10, M, 'At 9:40 she is on the factory floor with a phone. The same home screen fits it.'),
    (11, 11, M, 'She taps the microphone and asks out loud:'),
    (12, 13, P, '(the AI agent answers aloud: order five, TrendCart, knitting, due 20 April)'),
    (14, 14, M, 'The speaker button keeps spoken replies on for every answer.'),
    (15, 15, M, 'A harder question:'),
    (16, 16, P, '(the AI agent answers aloud: Northwind Apparel, eight thousand pieces)'),
    (17, 17, M, 'Actions work by voice too:'),
    (18, 18, P, '(the AI agent answers aloud: a draft is ready, nothing has been sent)'),
    (19, 19, M, 'Still only a draft. She says:'),
    (20, 20, M, 'A spoken send now is never sent. It waits for her tap, so a misheard word cannot send an email.'),
    (21, 21, M, 'Every page fits the phone: tables scroll inside their card, and buttons are thumb-sized.'),
    (22, 22, M, 'Back at the desk. Was yesterday’s assembly output normal?'),
    (23, 23, M, 'No: 455 pieces, against 687 to 807 on the last eight Tuesdays. That is 39% below.'),
    (24, 24, M, 'A vague question: TrendCart has six active orders, so it asks instead of guessing.'),
    (25, 25, M, 'Only one is a scarf: order 5. Show more lists each tool call and the rows behind the answer.'),
    (26, 26, K, '11:15. A customer wants 800 hoodies by the 25th.'),
    (27, 27, K, 'It asks the one thing that changes the answer: ready at the factory, or delivered?'),
    (28, 28, K, 'An estimate, not a yes: unlikely. The queue finishes on 30 April.'),
    (29, 29, K, 'The Feasibility page runs the same tool over the whole queue: the same 30 April, and it shows why.'),
    (30, 30, K, '2:30, the core task: chase a stalled order, typed the way it is said on the floor.'),
    (31, 31, K, 'It checks her claim against the record first: 8 days without activity, true. Then it drafts to knitting.'),
    (32, 32, K, 'Preview first. Nothing is sent until she confirms this exact draft.'),
    (33, 33, K, 'Confirmed and sent. On the live system it leaves from her own mailbox.'),
    (34, 34, K, 'A standing watch: tomorrow at ten the server checks, and tells her only if nobody replied.'),
    (35, 35, K, 'Every action is logged, with recipient, orders and subject.'),
    (36, 36, K, 'Honesty under pressure. A question the data cannot answer:'),
    (37, 37, K, 'No prices in the records, so no revenue figure. It says what it can answer instead.'),
    (38, 38, K, 'A wrong premise: the record says order 29 moved today. It says so, and asks before writing.'),
    (39, 39, K, 'Order 218 is not in the records, and it says so. It never invents one.'),
    (40, 40, K, 'Every number comes from a tool. It asks instead of guessing. By voice or by hand, nothing leaves without her.'),
]

# Presentation_Group19.mp4 (Sprint 3, 4:49) — cues from Presentation_Group19.srt
PRESENTATION = [
    (0, 1, W, 'Good afternoon. We are Group 19, Track 1, and this is ThreadPilot, the manager’s co-pilot.'),
    (2, 5, W, 'Our user is the general manager of a knitwear factory. She runs it on the move, without SQL, and the '
              'questions start at seven: did anything go wrong, how is TrendCart’s order, can we take 800 hoodies? '
              'That costs seventy-three planner-hours a month, and eight of thirty-four open orders are already late. '
              'ThreadPilot answers from the records, and acts only when she confirms.'),
    (6, 6, W, 'Seven o’clock. The day is on one screen.'),
    (7, 7, W, 'Red: eight overdue, three decisions waiting.'),
    (8, 8, W, 'Review options simulates moving order 29 up.'),
    (9, 9, W, 'It would make six other orders later, so it says: keep the order.'),
    (10, 10, W, 'It has also drafted chase-ups for the two stalled orders, from the records.'),
    (11, 11, W, 'Review and send opens the preview. She checks it, and confirms.'),
    (12, 12, W, 'Sent and logged. Nothing went out before her click.'),
    (13, 14, W, 'Every chart explains itself: normal means the last eight same weekdays.'),
    (15, 15, W, 'The seven o’clock briefing: each point with its records.'),
    (16, 16, W, 'Nine forty, on the floor, in her own words.'),
    (17, 17, W, 'TrendCart has six orders, so it asks instead of guessing.'),
    (18, 18, W, 'The scarf one: order five.'),
    (19, 19, W, 'Show more: every tool call, and the rows behind it.'),
    (20, 20, M, 'Eleven fifteen. 800 hoodies by the 25th?'),
    (21, 21, M, 'It asks the one thing that changes the answer: at the factory, or delivered?'),
    (22, 22, M, 'Then an estimate, with outside workshops. Not a promise.'),
    (23, 23, M, 'Two thirty: the core task. Chase a stalled order, in her own words.'),
    (24, 24, M, 'It checks her claim first: eight days without activity, true. Then it drafts to knitting.'),
    (25, 25, M, 'Preview first. Nothing is sent until she confirms.'),
    (26, 26, M, 'Confirmed, sent from her own mailbox, and logged.'),
    (27, 27, M, 'Remind me tomorrow if they don’t reply: a watch the server checks at ten.'),
    (28, 28, M, 'Alerts speak first, but rationed: at most three a day.'),
    (29, 29, M, 'Hard case one: a wrong premise about order 29.'),
    (30, 30, M, 'It moved today. It says so, and asks.'),
    (31, 31, M, 'Hard case two: no order number, only a description.'),
    (32, 32, M, 'Three orders match, so it lists them instead of picking one.'),
    (33, 33, M, 'The vest one: order 120. Drafted, not sent.'),
    (34, 34, M, 'Hard case three: an order that doesn’t exist.'),
    (35, 35, M, 'Not in the records, and it says so.'),
    (36, 36, K, 'We tested against ground truth: seventy new questions written from the data files only, every answer '
                'computed twice and checked, run once with no fixes. Sixty-nine percent fully correct, with a confidence '
                'interval of fifty-seven to seventy-eight. Production and normal-range questions: ten of ten. '
                'Not-in-the-records: seven of eight. But rankings and comparisons: three of eight each. Without the '
                'language model, twenty-one percent. With eight to ten questions per type, read the categories as '
                'indicative. And in thirteen hundred graded runs, no email went out without a confirmed preview.'),
    (37, 37, K, 'What breaks it? Nine misses need a ranking or filter we never built, like oldest by order date. Seven '
                'are order numbers it can’t read, like hash eighty-one, or eighty-three or two. Three comparisons give a '
                'table but no verdict. The pattern: one question, one tool, it is right. Next we build one '
                'sort-and-filter tool, fix the number parsing, and run these seventy on the live model.'),
    (38, 38, K, 'We built an all-day co-pilot. On questions it had never seen, it was right sixty-nine percent of the '
                'time, never sent an email without a confirmed preview, and never invented a record. We learned that a '
                'tuned score is a regression check, not accuracy; rules belong in code; and misses cluster. Thank you.'),
]
