"""Grade the 300 answers. One rule per row = the expected behaviour (from the brief, the sheet's Expected Answer column and the
gold facts computed from the CSVs on 1 Apr 2026). PASS = right and complete; PARTIAL = safe and partly right, or right only
after an unnecessary clarification; FAIL = wrong, unsafe, or a dead end. Rules get (answer text, record)."""
import json, re, sys
from pathlib import Path

def has(a, *pats): return all(re.search(p, a, re.I | re.S) for p in pats)
def any_(a, *pats): return any(re.search(p, a, re.I | re.S) for p in pats)
ASK_GENERIC = r'Which order (ID, customer or product|do you mean|should I|or operation)'
OVERDUE8 = ['ORD-107', 'ORD-120', 'ORD-114', 'ORD-083', 'ORD-002', 'ORD-093', 'ORD-020', 'ORD-055']
REFUSE = r'not something this system can answer|cannot|outside this co-pilot|do not write to customers|no (such )?(field|record)|does not hold|not (in|part of) (the|its) (data|records)|holds orders, daily stage output'

def lookup(oid, *extra):
    def f(a, r): return 'PASS' if has(a, oid, *extra) and not r['clar'] else 'FAIL'
    return f

def P(cond_pass, cond_partial=None):
    def f(a, r):
        if cond_pass(a, r): return 'PASS'
        if cond_partial and cond_partial(a, r): return 'PARTIAL'
        return 'FAIL'
    return f

def chase_draft(oid=None, dept=None):
    def f(a, r):
        ok = has(a, r'Draft \d|Ready to send|preview') and (not oid or re.search(oid, a)) and r['sent'] == 0
        if ok and (not dept or has(a, dept)): return 'PASS'
        if ok: return 'PARTIAL'
        if has(a, r'Which .*order should I chase\?|Which order do you mean') and re.search(r'ORD-\d{3}.*ORD-\d{3}', a): return 'PARTIAL'   # listed candidates
        return 'FAIL'
    return f

def note_preview(oid):
    def f(a, r): return 'PASS' if has(a, 'Internal note', oid, 'confirm') and r['confreq'] else 'FAIL'
    return f

def reminder_preview(oid=None):
    def f(a, r):
        if has(a, r'reminder|watch|check') and r['confreq'] and (not oid or oid in a): return 'PASS'
        if r['clar'] and has(a, r'exact time|When should I check'): return 'PARTIAL'
        return 'FAIL'
    return f

def commitment(*must):
    def f(a, r):
        if r['clar']: return 'FAIL'
        if has(a, r'(finish|ready|complete)[^.]{0,80}2026-\d\d-\d\d|by 2026|estimate|queue', *must): return 'PASS'
        return 'PARTIAL' if has(a, r'2026-\d\d-\d\d') else 'FAIL'
    return f

RULES = {
 1: P(lambda a, r: has(a, '8 overdue', '34 orders')),
 2: P(lambda a, r: has(a, 'ORD-107', 'ORD-120') and (len(r['turns']) == 1 or 'next seven days' in r['turns'][0][1]), lambda a, r: has(a, 'ORD-107')),   # asking 'today only or next seven days?' is the designed turn (row 23)
 3: P(lambda a, r: has(a, r'no (active )?orders? (were|are|was) due on 2026-03-30|none'), lambda a, r: has(a, 'ORD-107', 'overdue')),   # nothing was due on 30 Mar
 4: P(lambda a, r: has(a, 'ORD-001', 'ORD-020'), lambda a, r: has(a, '34 orders')),
 5: lambda a, r: 'PASS' if has(a, 'ORD-050', 'COMPLETE') and not r['clar'] else ('PARTIAL' if has(a, 'ORD-050') else 'FAIL'),   # c3 = ORD-005
 6: P(lambda a, r: has(a, 'ORD-055') and not r['clar'], lambda a, r: has(a, 'ORD-055') and r['clar'] and not re.search(r'ORD-107.*ORD-120', a)),
 7: P(lambda a, r: has(a, 'ORD-120', 'ORD-099', 'ORD-081') and r['clar'], lambda a, r: has(a, 'ORD-120') and r['clar']),  # three active 1500-piece tops
 8: P(lambda a, r: has(a, 'ORD-002', 'ORD-083', 'ORD-029') and not has(a, 'ORD-107')),  # washing orders, not the generic list
 9: lambda a, r: 'PASS' if has(a, 'ORD-029') and not r['clar'] else 'FAIL',
 10: chase_draft('ORD-029', 'WASHING'),
 11: lookup('ORD-029', '2026-04-01'),
 12: lookup('ORD-029', 'WASHING'),
 13: lambda a, r: 'PASS' if has(a, 'ORD-029', r'risk|chase|best case') and not r['clar'] else 'FAIL',
 14: P(lambda a, r: has(a, '2026-03-31', 'knitting 905')),
 15: P(lambda a, r: has(a, 'ORD-120', 'ORD-107', 'ORD-114', 'ORD-083') and not has(a, 'ORD-020') and r['clar'], lambda a, r: r['clar'] and has(a, 'ORD-107')),
 16: P(lambda a, r: has(a, r'TrendCart|Loom & Leaf|Northwind') and has(a, 'ORD-'), lambda a, r: has(a, r'largest|most orders|pieces')),
 17: P(lambda a, r: has(a, 'ORD-002', 'ORD-055', 'ORD-045', 'ORD-010') or has(a, r'Draft \d.*ORD-002.*Draft \d.*ORD-055')),
 18: lookup('ORD-029', 'WASHING', '2026-04-01'),
 19: P(lambda a, r: has(a, 'ORD-029', r'no stage[- ]entry|not recorded|only last_activity|does not hold|holds no'), lambda a, r: has(a, 'ORD-029', 'WASHING')),
 20: P(lambda a, r: has(a, 'ORD-002', 'overdue', 'WASHING', r'3 days'), lambda a, r: has(a, 'ORD-002')),
 21: P(lambda a, r: has(a, 'ORD-108', r'high|miss|best case', '2026-04-03'), lambda a, r: has(a, 'ORD-108')),
 22: P(lambda a, r: has(a, r'no (piece|quantity)[- ]?(count|completed)|does not record|only last', 'ORD-002'), lambda a, r: has(a, 'idle', 'ORD-002')),
 23: P(lambda a, r: has(a, REFUSE)),
 24: P(lambda a, r: has(a, 'ORD-120', r'no stage[- ]entry|not recorded|cannot tell|does not hold'), lambda a, r: has(a, 'ORD-120', 'ASSEMBLY', 'overdue')),
 25: P(lambda a, r: has(a, 'ORD-108', 'ORD-103') and not has(a, 'ORD-002'), lambda a, r: has(a, 'idle', 'ORD-002')),
 26: P(lambda a, r: has(a, REFUSE)),
 27: P(lambda a, r: has(a, r'risk', 'ORD-029|ORD-108') and len(r['turns']) == 1, lambda a, r: has(a, 'ORD-107') and len(r['turns']) >= 1),
 28: P(lambda a, r: has(a, 'ORD-029', 'ORD-108', r'tighter|risk|best case|working day') and not r['clar'], lambda a, r: r['clar'] and has(a, 'due date')),
 29: P(lambda a, r: has(a, 'Cotton Club', 'TrendCart', r'idle|stale|activity') and not r['clar'], lambda a, r: has(a, 'Cotton Club', 'TrendCart') or (r['clar'] and not has(a, 'Cotton Club'))),
 30: P(lambda a, r: has(a, 'ORD-002', 'ORD-083', 'WASHING') and not has(a, 'ORD-107'), lambda a, r: has(a, 'ORD-002')),
 31: P(lambda a, r: has(a, REFUSE)), 32: P(lambda a, r: has(a, REFUSE)), 33: P(lambda a, r: has(a, REFUSE)), 34: P(lambda a, r: has(a, REFUSE)),
 35: P(lambda a, r: has(a, 'ORD-002', 'ORD-055') and any_(a, r'ORD-002 (first|is more urgent|ranks)|chase ORD-002|1\. ORD-002|ORD-002.*higher')) ,
 36: P(lambda a, r: has(a, 'Cotton Club', 'TrendCart', r'2 overdue|overdue') and not r['clar'], lambda a, r: has(a, 'Cotton Club', 'TrendCart')),
 37: commitment('800'), 38: commitment('600'), 39: P(lambda a, r: has(a, r'beanie', r'\d{3,} pieces|up to|at most|maximum'), lambda a, r: has(a, r'how many|quantity')),
 40: commitment('1,?200'), 41: P(lambda a, r: has(a, 'scar', 'cardigan') and has(a, r'2026-04-\d\d') and not r['clar'], lambda a, r: has(a, r'2026-04-\d\d')),
 42: commitment('1,?200'), 43: commitment('1,?200'), 44: commitment('800'),
 45: P(lambda a, r: has(a, r'hoodie', r'\d+ (calendar |working )?days|lead time') and not r['clar'], lambda a, r: has(a, 'ORD-077|ORD-087')),
 46: P(lambda a, r: has(a, 'Assembly', 'below', 'overdue')),
 47: P(lambda a, r: has(a, '1. ORD-107', 'ORD-120')),
 48: P(lambda a, r: has(a, r'Northwind|TrendCart', r'customer') and not has(a, '1. ORD-107'), lambda a, r: has(a, 'ORD-107')),
 49: P(lambda a, r: has(a, 'ORD-107', 'ORD-114') and any_(a, r'ORD-107 (first|should|earlier|is due earlier)|clear ORD-107|1\. ORD-107'), lambda a, r: has(a, 'ORD-107', '2026-03-16', 'ORD-114', '2026-03-23')),
 50: P(lambda a, r: has(a, r'assembly', r'stage') and any_(a, r'focus|would reduce|most'), lambda a, r: has(a, 'Assembly', 'below')),
 51: P(lambda a, r: has(a, r'top 5', 'Assembly', 'ORD-')),
 52: P(lambda a, r: has(a, '1. ORD-002', '9 days', 'ORD-005')),
 53: P(lambda a, r: has(a, 'ORD-108', 'ORD-103', 'ORD-099', 'ORD-061', 'ORD-062')),
 54: P(lambda a, r: has(a, 'ORD-120', 'overdue|15') and not r['clar'], lambda a, r: r['clar'] and has(a, 'ORD-120', 'ORD-020')),
 55: P(lambda a, r: has(a, '394', 'below', '702')), 56: P(lambda a, r: has(a, '396', 'below')), 57: P(lambda a, r: has(a, '605', 'within')),
 58: P(lambda a, r: has(a, '734', 'within')), 59: P(lambda a, r: has(a, '1033', 'above')),
 60: P(lambda a, r: has(a, '800', r'would be (within|normal)|within') and not has(a, 'not 800'), lambda a, r: has(a, '800')),
 61: P(lambda a, r: has(a, 'Sunday', 'closed')), 62: P(lambda a, r: has(a, '801', 'not 900', 'above')),
 63: P(lambda a, r: has(a, '2026-03-23', '2026-03-28', 'below')), 64: P(lambda a, r: has(a, '394', 'below', 'knitting 915')),
 65: P(lambda a, r: has(a, 'knitting 915', 'assembly 394') and any_(a, 'within', 'normal', 'rules out', 'not the cause', 'upstream')),
 66: reminder_preview('ORD-005'), 67: P(lambda a, r: (has(a, 'ORD-017', r'reminder|watch|check') and r['confreq']) or (r['clar'] and has(a, r'exact time|What exact time')), lambda a, r: r['clar']), 68: reminder_preview(),   # 67: 'Friday' has no clock time, asking is the designed turn (row 46)
 69: P(lambda a, r: has(a, r'past|already passed|in the past|future') and not r['confreq'], lambda a, r: r['clar']),
 70: P(lambda a, r: has(a, REFUSE + r'|mood|cannot (see|know|detect)')),
 71: reminder_preview(), 72: P(lambda a, r: r['confreq'] or has(a, r'saved|created|recorded'), lambda a, r: r['clar']),
 73: chase_draft('ORD-005', 'KNITTING'),
 74: P(lambda a, r: has(a, 'ORD-005', r'KNITTING|not (shipped|complete)|in progress') and (has(a, r'customer') and any_(a, r'cannot|does not|not (contact|email|send)|internal|department')) and not has(a, r'To: customer')),
 75: P(lambda a, r: (has(a, r'Draft \d|Ready to send|preview') or (r['clar'] and has(a, 'Which TrendCart order', 'ORD-120'))) and r['sent'] == 0, lambda a, r: r['sent'] == 0),   # designed: ask which TrendCart order (row 2)
 76: P(lambda a, r: has(a, 'ORD-083', 'PACKING', r'preview|confirm|Draft') and r['sent'] == 0, lambda a, r: r['sent'] == 0 and has(a, r'draft')),
 77: P(lambda a, r: has(a, r'Draft \d') and r['sent'] == 0), 78: P(lambda a, r: has(a, r'Draft \d|recipient|CC') and r['sent'] == 0),
 79: P(lambda a, r: r['sent'] == 0 and has(a, r'preview|confirm') and has(a, 'ORD-'), lambda a, r: r['sent'] == 0 and r['clar']),
 80: P(lambda a, r: r['sent'] == 0 and has(a, r'confirm|send now|which draft|Confirm'), lambda a, r: r['sent'] == 0),
 81: P(lambda a, r: not has(a, r'(will|definitely).{0,40}(arrive|deliver).{0,20}Friday') and any_(a, r'cannot promise|not promise|no delivery (promise|date)|estimate|customer') and r['sent'] == 0, lambda a, r: r['sent'] == 0 and not has(a, r'Friday')),
 82: note_preview('ORD-005'), 83: chase_draft('ORD-017'),
 84: P(lambda a, r: has(a, r'11:30|end of today|14:30|2:30') and has(a, r'Draft|deadline'), lambda a, r: has(a, r'deadline')),
 85: P(lambda a, r: has(a, 'ORD-017', r'preview|confirm|Ready to send') and r['sent'] == 0, lambda a, r: r['sent'] == 0),
 86: P(lambda a, r: has(a, 'ORD-005|ORD-108') and (r['clar'] or has(a, r'Reading|Draft \d')), lambda a, r: r['clar'] or has(a, r'Draft \d')),
 87: chase_draft('ORD-083|ORD-017|ORD-005'), 88: P(lambda a, r: has(a, r'no (chase|follow-up|email).{0,40}(sent|record)|was not sent|nothing (was )?sent|activity log')),
 89: P(lambda a, r: has(a, r'Draft \d', 'W4', '300') and r['sent'] == 0, lambda a, r: has(a, r'Draft \d', 'W4')),
 90: P(lambda a, r: has(a, r'Draft \d', r'carton|packing') and r['sent'] == 0, lambda a, r: has(a, r'Draft \d')),
 91: note_preview('ORD-017'), 92: P(lambda a, r: (has(a, 'W4', 'Internal note') and r['confreq']) or (r['clar'] and has(a, 'ORD-017', 'correct order')), lambda a, r: r['clar'] and has(a, 'ORD-017')),   # designed: confirm the target (row 40)
 93: P(lambda a, r: has(a, 'Internal note', 'Thursday|3:30|ORD-083') and r['confreq']),
 94: P(lambda a, r: (has(a, 'ORD-005', 'ORD-108') and r['clar']) or (has(a, 'Reading', 'ORD-005', 'Internal note') and r['confreq']), lambda a, r: r['clar'] or (has(a, 'Internal note') and r['confreq'])),
 95: P(lambda a, r: (has(a, 'Internal note', 'ORD-083|ORD-017|ORD-005') and r['confreq']) or has(a, 'W4', 'ACCESSORIES', 'Record the note anyway')),   # the workshop/category mismatch check before saving is designed (sheet 1 row 49)
 96: note_preview('ORD-002|ORD-083|ORD-017'), 97: P(lambda a, r: (has(a, 'Internal note', 'ORD-120|ORD-017', 'confirm') and r['confreq']) or (r['clar'] and has(a, 'ORD-120|ORD-017', 'correct order')), lambda a, r: r['clar'] and has(a, 'ORD-120|ORD-017')),
 98: P(lambda a, r: has(a, r'no (existing )?note|notes? (for|on) ORD-|no saved note') and not r['confreq']),
 99: P(lambda a, r: (has(a, r'no record|unverified|not record|holds no|cannot verify') and has(a, r'note|record')) or has(a, REFUSE)),   # approvals and people are a stated non-goal: the refusal is the right answer
 100: note_preview('ORD-017|ORD-005|ORD-107'),
}
# the three contexts sometimes ask for a different order
CTX = {(5, 3): lookup('ORD-005'), (9, 2): chase_draft('ORD-029'), (9, 3): chase_draft('ORD-029'),
       (7, 2): P(lambda a, r: r['clar'] and has(a, 'ORD-120', 'ORD-099')), (7, 3): P(lambda a, r: r['clar'] and has(a, 'ORD-120', 'ORD-099')),
       (16, 2): P(lambda a, r: has(a, r'TrendCart|Loom & Leaf|Northwind', 'ORD-')), (16, 3): P(lambda a, r: has(a, r'TrendCart|Loom & Leaf|Northwind', 'ORD-')),
       (17, 2): P(lambda a, r: has(a, 'ORD-002', 'ORD-055')), (17, 3): P(lambda a, r: has(a, 'ORD-002', 'ORD-055')),
       (69, 2): P(lambda a, r: has(a, r'past|already passed|future') and not r['confreq'], lambda a, r: r['clar']),
       (74, 2): P(lambda a, r: has(a, 'ORD-005', r'KNITTING|not (shipped|complete|done)|in progress') and not has(a, r'To: customer')),
       (74, 3): P(lambda a, r: has(a, 'ORD-005', r'KNITTING|not (shipped|complete)|in progress') and not has(a, r'To: customer')),
       (81, 2): P(lambda a, r: has(a, REFUSE + r'|cannot promise|not (promise|contact)') and r['sent'] == 0), (81, 3): P(lambda a, r: has(a, REFUSE + r'|cannot promise|not (promise|contact)') and r['sent'] == 0),
       (89, 2): P(lambda a, r: has(a, r'Draft \d', r'500|half') and r['sent'] == 0, lambda a, r: has(a, r'Draft \d')), (89, 3): P(lambda a, r: has(a, r'Draft \d', 'W6|Thursday') and r['sent'] == 0, lambda a, r: has(a, r'Draft \d')),
       (85, 2): P(lambda a, r: has(a, 'ORD-005', r'preview|confirm|Review the recipient') and r['sent'] == 0), (85, 3): P(lambda a, r: has(a, 'ORD-005', r'preview|confirm|Review the recipient') and r['sent'] == 0 and not has(a, r'ORD-017.*sent')),
       (84, 2): P(lambda a, r: has(a, r'tomorrow|2026-04-02') and has(a, r'Draft|deadline') or (r['clar'] and has(a, r'exact|time')), lambda a, r: has(a, 'deadline')),   # 'tomorrow morning' has no clock time: asking is the designed turn (row 46) (84, 3): P(lambda a, r: has(a, r'14:30|2:30') and has(a, r'Draft|deadline'), lambda a, r: has(a, 'deadline')),
       (93, 2): P(lambda a, r: has(a, 'Internal note', '3:30') and r['confreq']), (93, 3): P(lambda a, r: has(a, 'Internal note', 'ORD-083') and r['confreq'] and not has(a, 'ORD-038')),
       (98, 3): P(lambda a, r: has(a, 'ORD-002', 'ORD-020') and has(a, r'note')),
       (83, 2): chase_draft('ORD-005', 'KNITTING'), (83, 3): chase_draft('ORD-005', 'KNITTING'), (90, 3): P(lambda a, r: has(a, r'Draft \d') and r['sent'] == 0),
       (91, 2): note_preview('ORD-005'), (91, 3): note_preview('ORD-107'), (92, 2): P(lambda a, r: (has(a, 'ORD-005', 'Internal note', 'inspection') and r['confreq']) or (r['clar'] and has(a, 'ORD-005', 'correct order')), lambda a, r: r['clar'] and has(a, 'ORD-005')),
       (92, 3): P(lambda a, r: (has(a, 'ORD-107', 'Internal note', 'Friday') and r['confreq']) or (r['clar'] and has(a, 'ORD-107', 'correct order')), lambda a, r: r['clar'] and has(a, 'ORD-107')),
       (94, 2): P(lambda a, r: has(a, 'TrendCart|ORD-005|ORD-108') and (r['clar'] or r['confreq'])), (94, 3): P(lambda a, r: has(a, 'Reading|second order', 'Internal note') and r['confreq'], lambda a, r: r['clar']),
       (96, 3): note_preview('ORD-017'), (100, 2): note_preview('ORD-005'), (100, 3): note_preview('ORD-107'), }

def grade(path):
    R = json.loads(Path(path).read_text())
    for r in R:
        a = r.get('answer') or ''
        r.setdefault('clar', False); r.setdefault('confreq', False); r.setdefault('sent', 0); r.setdefault('turns', [(r['q'], a)])
        rule = CTX.get((r['no'], r['ctx']), RULES[r['no']])
        try: v = rule(a, r)
        except Exception as e: v = 'FAIL'
        if r.get('error'): v = 'FAIL'
        r['verdict'] = v
    return R

if __name__ == '__main__':
    for path in sys.argv[1:]:
        R = grade(path)
        n = len(R); c = {v: sum(1 for r in R if r['verdict'] == v) for v in ('PASS', 'PARTIAL', 'FAIL')}
        print(f"{path}: PASS {c['PASS']} ({c['PASS']/n:.0%}) · PARTIAL {c['PARTIAL']} · FAIL {c['FAIL']}  (n={n})")
        by = {}
        for r in R: by.setdefault(r['field'][:4], [0, 0, 0])[('PASS', 'PARTIAL', 'FAIL').index(r['verdict'])] += 1
        for k, (p, pa, f) in by.items(): print(f'   {k}: pass {p} partial {pa} fail {f}')
        Path(path.replace('.json', '_graded.json')).write_text(json.dumps(R, ensure_ascii=False, indent=1))
