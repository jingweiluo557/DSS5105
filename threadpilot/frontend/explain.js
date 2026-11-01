/* The "i" button beside every visualisation and calculation: what it shows, how to read it, and why it is done that way.
   One place for the rationale, so the manager never has to ask; the wording follows the code it describes
   (services/home_service.py, queue_engine.py, alert_policy.py, baseline_rationale.py, analysis/*.py).
   Usage: infoButton('pulse') inside a heading; the click handler below opens the explanation next to the button. */
(function () {
  const WHY_EIGHT = 'The factory is closed on Sundays and each weekday runs at its own level, so a day is compared with its own weekday. Measured on this factory’s data, eight weeks cuts false alerts from about 0.67 to 0.1 a month while still catching real drops; 10 to 12 weeks add little and need more history than the 90 days hold.';
  window.EXPLAIN = {
    status: { title: 'The status line',
      shows: 'The whole factory in one line: the date, one colour, and the three facts behind the colour.',
      read: 'RED means a decision today changes the outcome. AMBER means decide today, nothing is lost yet. GREEN means nothing needs you; the briefing has the detail.',
      why: 'The colour is set by the same rules as the alert emails (red when an urgent P1 item exists, amber when only P2 items do), so the screen and your inbox never disagree. A review found no screen said what to decide in the first ten seconds; this line does.' },
    decide: { title: 'Decide today',
      shows: 'At most three things that need your decision today, each with the numbers behind it and one next step.',
      read: '"Act now" cards are urgent (P1): a stage far outside its range, a stage below range three working days in a row, or an order that will miss its date even in the best case. "Decide today" cards (P2) can wait for the 14:00 digest.',
      why: 'They are the alert policy’s findings, ranked by score. More than three would be a list, not a decision; the rest wait in the briefing and under Risk orders.' },
    health: { title: 'Order health',
      shows: 'Every order in production, split into three words: late, at risk, on track.',
      read: 'Late = past its due date. At risk = the queue simulation says it finishes after its due date (high: 5 or more working days late even in the best case; medium: 1 to 4, or late only if new orders keep arriving). On track = finishes before the due date even with new orders arriving. The on-time figure counts completed orders in the last 30 days against the 30 days before.',
      why: 'Before this, the app had four different risk scales. One vocabulary, from one simulation, means "at risk" means the same thing on every screen and in the chat. In a test on simulated futures, orders labelled high risk finished late 96% of the time and low risk 4%.' },
    pulse: { title: 'Production pulse',
      shows: 'The latest working day’s output for each stage, against that stage’s normal range.',
      read: 'The grey band runs from the lowest to the highest output on the previous eight same weekdays. A blue bar inside the band is a normal day; a red bar below it is below range, with the percentage under the mean and how many working days it has been below.',
      why: 'A single number says nothing without a sense of normal. ' + WHY_EIGHT + ' One day below range happens by chance about one time in nine, so it is only a watch item; three working days in a row (about one in 729) or a single day more than 3.5 standard deviations under the mean is what triggers an alert.',
      ask: 'Why do you use eight same weekdays?' },
    trend: { title: 'Stage output trend',
      shows: 'The last ten working days of one stage, with its baseline line.',
      read: 'Points under the line are days below the stage’s usual level; a run of them is what the alert rule looks for.',
      why: WHY_EIGHT, ask: 'Why do you use eight same weekdays?' },
    briefing: { title: 'Morning briefing',
      shows: 'What happened yesterday, what is at risk, and what to decide, written at 07:00 from the records.',
      read: 'Each section is one paragraph; "Open the full briefing" shows the records each paragraph used. Its decisions become today’s to-do list.',
      why: 'The language model writes the words from a packet of facts our code computed; it never computes a number itself. Every number in the text must appear in the packet, and a second model call audits the text against the facts. If either check fails, the briefing is not saved.' },
    todos: { title: 'Your to-dos',
      shows: 'Items you added, plus the briefing’s decisions that name an order or a stage.',
      read: 'Tick an item to record it as handled; it stays in the record.',
      why: 'The briefing’s advice only counts if it turns into something you can do and close.' },
    ask: { title: 'How the chat answers',
      shows: 'A question in plain words becomes a sourced answer.',
      read: 'The model works out what kind of question it is; our code looks up and calculates every number from the records; the model puts the facts into words. "Show more" under an answer lists each step, and Sources opens the exact rows.',
      why: 'A language model is good at understanding messy questions and poor at arithmetic and exact recall. Letting it choose the question type but never a number means any figure you read can be traced to a record. In our 88-question test, 0 of 2,117 stated numbers lacked a source.' },
    steps: { title: 'How this answer was made',
      shows: 'The steps behind the answer, in order: memory, the planner’s reading, each tool call with its inputs, result, source rows and time, then the narration.',
      read: 'Purple-tinted steps are the language model; the rest are our code. "Recalling" means a phrase such as "the first one" was resolved from this conversation, and the answer says which order it took.',
      why: 'Trust comes from being able to check. Anyone can see that a number came from a tool and a record, not from the model.' },
    capacity: { title: 'Capacity picture',
      shows: 'For the order you asked about: at each stage, the work already queued ahead of it plus this order, against what the stage can finish by the due date.',
      read: 'A bar past its capacity line (red) is a stage that cannot clear its queue plus this order in time. Stages run one after another, so the finish date comes from the queue simulation, not from adding the bars.',
      why: 'It answers the question that follows "unlikely": where is the bottleneck? Capacity per day is the stage’s usual output on the previous eight same weekdays, adjusted by how much of planned volume the stage has completed historically. ' + WHY_EIGHT, ask: 'Why do you use eight same weekdays?' },
    scenarios: { title: 'The shared estimate',
      shows: 'Three ways to meet the request: our own queue, the earliest eligible outside workshop, and a smaller order.',
      read: 'The date is where the queue simulation puts the new order (earliest due date first, your manual priorities kept, one order using at most 60% of a stage’s day, Sundays skipped). The on-time chance comes from a separate lead-time model fitted on the 86 completed orders (it ranks well, AUC 0.90, but is less exact near 50%, so read a mid value as "uncertain"). "Delivered to the customer" keeps two working days for shipping.',
      why: 'Options rather than a verdict, and the same tool the chat uses, so the page and the chat never give two different answers. The feasibility ranges were widened by three working days each side after a calibration study found the original ranges held only 7 times in 10 (now 94%).' },
    localmodel: { title: 'Cross-check: a simple queue proxy',
      shows: 'A rough local estimate: backlog at each stage divided by the stage’s average rate, run serially.',
      read: 'It is deliberately simple and usually more pessimistic than the shared estimate above, which is the one to act on.',
      why: 'Kept as a sanity check in the browser when the server is unreachable, and because two independent methods agreeing is worth more than one.' },
    priority: { title: 'Priority ranking',
      shows: 'Which active orders to look at first.',
      read: 'Overdue orders first, then the earliest due date; ties go to the older last activity, then the order ID. Each row says why it is where it is.',
      why: 'An explicit rule you can argue with, not an opaque score. A stated rule can be checked against the records in seconds.' },
    risk: { title: 'Risk orders',
      shows: 'Each active order’s risk level from the queue simulation, with its best-case finish date.',
      read: 'Late = past due. High = even in the best case it finishes 5 or more working days after the due date. Medium = 1 to 4 days late in the best case, or late only if new orders keep arriving. Low = finishes in time even with new orders arriving. "Best case" assumes no new orders join the queue.',
      why: 'The simulation replays the open orders through the four stages one working day at a time, earliest due date first with your priorities kept. The levels were tested on simulated futures: high risk finished late 96% of the time, low risk 4%, and the labels separate late from on-time orders far better than "the sooner it is due, the likelier it is late" (0.98 vs 0.67).' },
    expedite: { title: 'Dispatch decision',
      shows: 'What happens to the whole queue if this order jumps to the front.',
      read: 'Its finish date before and after; the lateness it saves; the lateness it pushes onto other orders; and the net, in order-working-days. The verdict is "keep the current order" unless the move saves at least two order-working-days net.',
      why: 'Expediting looks free when you only see the order you care about. Showing the cost to the other orders turns it into an honest trade-off, and every decision is recorded with the reviewer’s name and reason.' },
    workshops: { title: 'External workshop comparison',
      shows: 'Which outside workshops could take the batch, and when they would finish.',
      read: 'Only active workshops that make this product category are eligible; the finish date uses their stated capacity, queue and batch size. A workshop that does not cover every stage is flagged.',
      why: 'The records say what each workshop makes and how fast, not how well; defect history is shown so you can weigh it yourself.' },
    history: { title: 'Delivery history',
      shows: 'Completed orders and how many were late.',
      read: 'Late means completed after the due date. The home screen’s on-time rate uses the last 30 days against the 30 days before.',
      why: 'The same completed orders are what the lead-time model learns from, so this is also the model’s training record.' },
    alerts: { title: 'Alert emails',
      shows: 'Which findings would be emailed right now, and the rules that decide it.',
      read: 'P1 (email at once): a stage more than 3.5 standard deviations under its mean, a stage below range three working days in a row, an order that will miss even in the best case, or a customer whose orders all stopped. At most 3 a day; the same item is not emailed again within 24 hours unless it got worse. P2 waits for the 07:00 briefing or the 14:00 digest. P3 is shown in the app only. Quiet hours 22:00 to 06:00.',
      why: 'An alarm people learn to ignore protects nothing, so interruptions are rationed. The 3.5 SD threshold gives about 0.47 false alarms a month and catches a 40% one-day drop the same day 94% of the time (3.0 SD: 0.86 a month; 4.0 SD: 0.22 but misses more). Nothing is sent until you tick the box and Outlook is connected.',
      ask: 'Why do you use eight same weekdays?' },
    exceptions: { title: 'Exception monitoring',
      shows: 'A quick scan of measurable signals: a stage whose latest output is well under its recent mean, overdue orders, idle orders.',
      read: 'This list uses the browser\u2019s own simple rule, the previous 20 working days\u2019 mean, so its percentage differs slightly from the Production pulse and the alerts, which compare with the previous eight same weekdays (for example \u221235% here against \u221239% on the pulse for the same assembly day). Each card separates the signal from any assumption about its cause.',
      why: 'The scan is a fast first look that works even when the server is unreachable; the eight-same-weekday rule is the one that decides alerts because it respects the weekday pattern and the Sunday closure. ' + WHY_EIGHT,
      ask: 'Why do you use eight same weekdays?' },
    predictions: { title: 'Historical model predictions',
      shows: 'Imported outputs of an earlier experimental model.',
      read: 'Kept for comparison only; the Risk and Feasibility pages use the current queue simulation.',
      why: 'Keeping the old predictions visible lets you see where the two methods disagree instead of silently replacing one with the other.' },
    forecast: { title: 'Lead-time forecast',
      shows: 'For one order size: the typical lead time, a range, and the chance of finishing within the promised time.',
      read: 'The only input is the order size, because the records hold no stage-entry dates; a mid-range chance (40 to 60%) means "uncertain", not a coin flip.',
      why: 'A log-normal survival model fitted on the 86 completed orders, with the 34 open orders counted as "not finished yet" rather than ignored. It ranks late and on-time orders correctly nine times in ten (AUC 0.90).' },
    evidence: { title: 'Evidence used',
      shows: 'The exact rows of the source files behind this view.',
      read: 'Each row names its file and record number; the business date is fixed at 1 April 2026 so every figure can be reproduced.',
      why: 'Every number in the app traces to a row. If a figure cannot be traced, it is not shown.' }
  };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  window.infoButton = function (key) {
    const e = window.EXPLAIN[key]; if (!e) return '';
    return `<button type="button" class="info-btn" data-info="${key}" aria-label="Why ${esc(e.title.toLowerCase())} is shown this way" aria-haspopup="dialog" title="Why this way?">i</button>`;
  };
  let pop = null, opener = null;
  function close() { if (pop) { pop.remove(); pop = null; } if (opener && opener.isConnected) opener.focus(); opener = null; }
  function open(button) {
    const e = window.EXPLAIN[button.dataset.info]; if (!e) return;
    close(); opener = button;
    pop = document.createElement('div');
    pop.className = 'info-pop'; pop.setAttribute('role', 'dialog'); pop.setAttribute('aria-label', e.title);
    pop.innerHTML = `<div class="info-head"><strong>${esc(e.title)}</strong><button type="button" class="info-close" aria-label="Close">×</button></div>
      <dl><dt>What it shows</dt><dd>${esc(e.shows)}</dd><dt>How to read it</dt><dd>${esc(e.read)}</dd><dt>Why this way</dt><dd>${esc(e.why)}</dd></dl>
      ${e.ask && typeof window.ask === 'function' ? `<button type="button" class="small-button info-ask" data-ask="${esc(e.ask)}">Ask ThreadPilot: “${esc(e.ask)}”</button>` : ''}`;
    document.body.appendChild(pop);
    const r = button.getBoundingClientRect(), w = Math.min(380, innerWidth - 24);
    if (innerWidth < 640) { pop.style.left = '12px'; pop.style.right = '12px'; pop.style.bottom = '12px'; pop.style.top = 'auto'; }
    else {
      pop.style.width = w + 'px';
      pop.style.left = Math.max(12, Math.min(r.left, innerWidth - w - 12)) + 'px';
      const below = r.bottom + 8, h = pop.offsetHeight;
      pop.style.top = (below + h > innerHeight - 12 && r.top - h - 8 > 12 ? r.top - h - 8 : Math.min(below, innerHeight - h - 12)) + 'px';
    }
    pop.querySelector('.info-close').focus();
  }
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-info]');
    if (b) { e.preventDefault(); e.stopImmediatePropagation(); if (pop && opener === b) close(); else open(b); return; }
    if (!pop) return;
    if (e.target.closest('.info-close')) { e.preventDefault(); e.stopImmediatePropagation(); close(); return; }
    const askBtn = e.target.closest('.info-ask');
    if (askBtn) { e.preventDefault(); e.stopImmediatePropagation(); const q = askBtn.dataset.ask; close(); window.ask(q); return; }
    if (!e.target.closest('.info-pop')) close();
  }, true);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && pop) { e.stopImmediatePropagation(); close(); } }, true);
  addEventListener('hashchange', close);
})();
