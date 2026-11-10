"""Spoken lines for the two teleprompter videos (demo/make_prompter.py).

The burned-in captions are written to be read, and many run at 200-570 words a minute: too fast to say. These are the
lines to SAY, each anchored to the caption(s) on screen at that moment (cue indexes into the video's .srt) and short
enough to speak at about 145 words a minute inside that window. Edit freely; make_prompter.py warns when a line no
longer fits its window.

Each entry: (first_cue, last_cue, speaker, text). The line starts when first_cue appears and must be finished when
last_cue ends.
"""
W, M, K = 'Le Wenni (Wendy)', 'Foo Toon Ming (Matthew)', 'Kevin Royce Thomson'

# ThreadPilot_Demo.mp4 (the full product demo, 4:10) — cues from ThreadPilot_Demo.srt
DEMO = [
    (0, 0, W, 'ThreadPilot: one working day of a factory manager.'),
    (1, 1, W, 'At seven, the whole day is already on one screen.'),
    (2, 2, W, 'Each decision has one button. Review options simulates the queue.'),
    (3, 3, W, 'Moving order 29 up would make six others later, so it says: keep the order.'),
    (4, 4, W, 'It has also drafted chase-ups for the two stalled orders, straight from the records.'),
    (5, 5, W, 'Review and send opens the preview. She reads it, and confirms.'),
    (6, 6, W, 'Sent and logged. Nothing went out before her click.'),
    (7, 8, W, 'Every chart explains itself. Normal means the last eight same weekdays.'),
    (9, 9, W, 'The seven o’clock briefing: yesterday, today’s risks, today’s decisions, each with its records.'),
    (10, 10, W, 'Nine forty, on the floor. She asks: did anything go wrong yesterday?'),
    (11, 11, W, 'A discovery tool ranks thirty-four findings, so only the top five reach her. The assembly drop comes first.'),
    (12, 12, W, 'Was that normal? A written rule says no: 455 pieces, against 687 to 807 on the last eight Tuesdays.'),
    (13, 13, W, 'A vague question. TrendCart has six orders, so it asks instead of guessing.'),
    (14, 14, W, 'The scarf one: order five.'),
    (15, 15, M, 'Show more opens the planner’s reading, every tool call, and the exact rows behind the answer.'),
    (16, 16, M, 'A second order in the same chat: order 120, fifteen days overdue.'),
    (17, 17, M, 'Then the scarf one again. It remembers: not late yet, but the queue projects six working days late.'),
    (18, 18, M, 'A factory total? It refuses to add the stages.'),
    (19, 19, M, 'Eleven fifteen. Can we take 800 hoodies by the 25th?'),
    (20, 20, M, 'It asks the one thing that changes the answer: at the factory, or delivered?'),
    (21, 21, M, 'Then an estimate, not a yes, with its assumptions.'),
    (22, 22, M, 'The Feasibility page runs the same tool over the whole queue.'),
    (23, 24, M, 'Our queue finishes on the 30th, too late, but an outside workshop could make it. The chart shows why.'),
    (25, 25, M, 'Two thirty: the core task. Chase a stalled order, in her own words.'),
    (26, 26, M, 'It checks her claim first: eight days without activity, true. Then it drafts to knitting.'),
    (27, 27, M, 'Preview first. Nothing is sent until she confirms.'),
    (28, 28, M, 'Confirmed, and sent from her own mailbox.'),
    (29, 29, K, 'Remind me tomorrow if they don’t reply: a standing watch the server checks at ten.'),
    (30, 30, K, 'And every action lands in the Activity Log.'),
    (31, 31, K, 'Alerts speak first, but rationed: at most three a day.'),
    (32, 32, K, 'Now, honesty under pressure. What about revenue?'),
    (33, 33, K, 'There are no prices in the records, so no revenue figure. It says what it can answer instead.'),
    (34, 34, K, 'A wrong premise: she says order 29 is stuck. The record says it moved today, and it tells her.'),
    (35, 35, K, 'No order number, only a description: three orders match, so it asks.'),
    (36, 36, K, 'The vest one narrows it to order 120. Drafted, still not sent.'),
    (37, 37, K, 'Order 218 is not in the records. It says so.'),
    (38, 38, K, 'Every number traced. No guessing, no invention, nothing sent without her.'),
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
