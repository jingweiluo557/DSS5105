"""Run the held-out ground-truth set once through the real WorkflowEngine and grade it against the verified gold.

  python run_heldout.py ideal|fallback      -> heldout_<mode>.json (answers + verdicts) and a summary table
  python run_heldout.py ideal regression_2026-11-14   -> results/regression_2026-11-14_ideal.json: a later re-run kept
                                                         beside the frozen first run (the questions are then no longer unseen)

ideal    = the planner returns the reading in annotations_heldout.py (measures the server: routing, tools, wording)
fallback = the keyword planner the product uses when the model is down
Each item runs in its own fresh chat session; for multi-turn items only the last answer is graded.
Grading (from the gold written by the independent agent): PASS = expected behaviour, every must_include token, one of
each any_of group, no must_not_include token; PARTIAL = expected behaviour but a token missing, or a clarifying question
where an answer was expected; FAIL = wrong behaviour (answer where it should refuse/preview, a send, a wrong fact).
"""
import asyncio, json, re, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'q100'))   # reuses the engine set-up of evaluation/q100/run_q100.py
sys.argv = [sys.argv[0]] + sys.argv[1:]
import run_q100 as R   # noqa: E402  (engine, planners, mailbox stub, business clock 2026-04-01 12:00)
from annotations_heldout import A   # noqa: E402

ITEMS = json.loads((HERE / 'heldout.json').read_text())


class Planner(R.IdealPlanner):
    """The q100 planner stub reads IDs from the message; here the reading carries them, so pass them through once."""
    async def plan(self, message, state, now):
        sp = dict(self.spec); ids = sp.pop('order_ids', [])
        intent = R.Intent(sp.pop('intent')); slots = R.Slots(order_ids=ids, **sp)
        return R.Plan(tasks=[R.Task(message=message, classification=R.Classification(intent=intent, confidence=.95, slots=slots))])
SEND_WORDS = ['has been sent', 'have sent', "i've sent", 'email sent', 'was sent', 'message sent', 'sent it']


def norm(text):
    t = (text or '').replace('’', "'")
    return t.casefold()


def has_token(a, tok):
    tok_n = norm(str(tok))
    if re.fullmatch(r'\d+', tok_n):        # numbers: whole-number match, with or without thousands separators
        return bool(re.search(r'(?<![\d.,-])' + re.escape(tok_n) + r'(?![\d])', a.replace(',', '')))
    if re.fullmatch(r'ord-\d{3}', tok_n):
        return tok_n in a
    return tok_n in a


def grade(item, r):
    g = item['gold']; a = norm(r['answer'])
    if r.get('error'):
        return 'FAIL', 'server error: ' + r['error'][:80]
    if r['sent']:
        return 'FAIL', 'an email was sent'
    inc = all(has_token(a, t) for t in g.get('must_include', []))
    anyok = all(any(has_token(a, t) for t in grp) for grp in (g.get('any_of') or []))
    bad = [t for t in g.get('must_not_include', []) if has_token(a, t)]
    exp = g['expect']
    if exp == 'answer':
        if bad: return 'FAIL', 'wrong fact: ' + ', '.join(bad)
        if inc and anyok and not r['clar']: return 'PASS', ''
        if r['clar']: return 'PARTIAL', 'asked a question instead of answering'
        return 'FAIL', 'answer lacks the gold fact(s)'
    if exp == 'preview_no_send':
        if bad: return 'FAIL', 'claims it sent'
        if inc and anyok: return 'PASS', ''
        if r['clar'] and any(has_token(a, t) for t in g.get('must_include', [])[:1]): return 'PARTIAL', 'asked before drafting'
        return 'FAIL', 'no draft preview for the order'
    if exp == 'refuse':
        if anyok and not bad: return 'PASS', ''
        return 'FAIL', 'did not refuse'
    if exp == 'ask':
        if r['confreq']: return 'FAIL', 'proposed an action without the missing detail'
        if inc and anyok and r['clar']: return 'PASS', ''
        if r['clar']: return 'PARTIAL', 'asked, but not for the missing time'
        return 'FAIL', 'did not ask'
    if exp == 'reminder_preview':
        if bad: return 'FAIL', 'claims the reminder is already set'
        if inc and anyok and r['confreq']: return 'PASS', ''
        if r['clar']: return 'PARTIAL', 'asked instead of proposing the reminder'
        return 'FAIL', 'no reminder proposal'
    if exp == 'not_on_file':
        if anyok and not r['confreq']: return 'PASS', ''
        if r['clar']: return 'PARTIAL', 'asked a generic question instead of saying it is not on file'
        return 'FAIL', 'answered as if it existed'
    return 'FAIL', 'unknown expectation'


# Manual audit of the ideal run (9 Nov), applied after the automatic grade and listed beside it. Each override reads the
# full answer against the gold answer_text; the automatic token match is too generous in 7 cases and too strict in 2.
AUDIT = {
    'A05': ('FAIL', 'generic summary; no count of orders due 2026-04-11..19 (the matched "5" was incidental)'),
    'R06': ('FAIL', 'ranked by due date, not by order date; ORD-120 only appears as #2 of that list'),
    'R08': ('FAIL', 'stage filter ignored: ranked all stages, ORD-002 (washing) first'),
    'R02': ('PARTIAL', 'the right order is in the list but 10th, after the overdue ones; "next due after today" not answered'),
    'R04': ('PARTIAL', 'lists every customer with pieces; the verdict line answers "who needs attention", not "most pieces"'),
    'C02': ('PARTIAL', 'table of stages, no verdict on which is further along'),
    'C07': ('PARTIAL', 'table of stages, no verdict on which is closer to done'),
    'N08': ('PASS', '"No customer named Patagonia in the records" is the gold; the phrase list lacked this wording'),
    'M08': ('PASS', '"Not past due, not delayed yet: due 2026-04-01" is the gold; the phrase list lacked "not past due"'),
    'X03': ('FAIL', '"#83" not read as ORD-083, so no draft; nothing was sent (the auto-grader misread "nothing was sent")'),
}


# Regression run of 14 Nov, after the fixes that the 9 Nov failures led to (services/set_questions.py and friends). The 70
# questions are no longer unseen, so this run is a regression check, not a held-out accuracy. Read the same way: every
# answer against the gold answer_text. Three answers are right but worded outside the automatic phrase list.
AUDIT_REGRESSION = {
    'N07': ('PASS', '"SilkRoute is not a workshop on file … Nothing was drafted or sent" is the gold; the phrase list has "not on file" only as an unbroken phrase'),
    'N08': ('PASS', '"No customer named Patagonia in the records" is the gold; the phrase list lacked this wording'),
    'M08': ('PASS', '"Not past due, not delayed yet: due 2026-04-01" is the gold; the phrase list lacked "not past due"'),
}


async def run(mode, label=''):
    out = []
    audit = AUDIT_REGRESSION if label else AUDIT
    with tempfile.TemporaryDirectory() as tmp:
        for i, item in enumerate(ITEMS):
            sender = R.Sender()
            eng = R.WorkflowEngine(R.DataTools(R.B / 'data'), R.WorkflowStore(Path(tmp) / f'{mode}{i}.db'), lambda: R.NOW, sender)
            eng.email_scheduler = R.Mailbox()
            pl = Planner() if mode == 'ideal' else R.FallbackPlanner()
            st = R.DialogState(); eng.store.save(st)
            specs = A[item['id']]; specs = specs if isinstance(specs, list) else [specs]
            conf, resp, err = None, None, None
            for turn, spec in zip(item['turns'], specs):
                pl.spec = dict(spec)
                try:
                    resp = await eng.chat(R.ChatRequest(message=turn, session_id=st.session_id, confirmation_id=conf), pl)
                    conf = resp.confirmation_id
                except Exception as e:  # noqa: BLE001
                    err = f'{type(e).__name__}: {e}'; break
            r = dict(id=item['id'], category=item['category'], turns=item['turns'], gold=item['gold']['answer_text'], error=err,
                     answer=(resp.answer if resp and not err else ''), intent=(str(resp.intent) if resp else None),
                     clar=bool(resp and resp.needs_clarification), confreq=bool(resp and resp.confirmation_required),
                     sent=len(eng.email_scheduler.sent) + len(sender.sent))
            r['verdict'], r['why'] = grade(item, r)
            r['auto_verdict'] = r['verdict']
            if mode == 'ideal' and item['id'] in audit:
                r['verdict'], r['why'] = audit[item['id']][0], 'audit: ' + audit[item['id']][1]
            out.append(r)
    (HERE / 'results' / (f'{label}_{mode}.json' if label else f'heldout_{mode}.json')).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def table(rows):
    from collections import Counter, OrderedDict
    cats = OrderedDict()
    for r in rows: cats.setdefault(r['category'], Counter())[r['verdict']] += 1
    tot = Counter(r['verdict'] for r in rows)
    for c, n in cats.items():
        k = sum(n.values()); print(f"  {c:12s} {n['PASS']:2d}/{k:<2d} PASS ({n['PASS']/k:4.0%})  partial {n['PARTIAL']}  fail {n['FAIL']}")
    print(f"  {'TOTAL':12s} {tot['PASS']:2d}/{len(rows)} PASS ({tot['PASS']/len(rows):.0%})  partial {tot['PARTIAL']}  fail {tot['FAIL']}")


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'ideal'
    label = sys.argv[2] if len(sys.argv) > 2 else ''   # e.g. regression_2026-11-14: a separate file; heldout_<mode>.json is the frozen 9 Nov run
    rows = asyncio.run(run(mode, label))
    print(mode, 'audited' if mode == 'ideal' else ''); table(rows)
    if mode == 'ideal':
        print('automatic grade before the audit:'); table([dict(r, verdict=r['auto_verdict']) for r in rows])
