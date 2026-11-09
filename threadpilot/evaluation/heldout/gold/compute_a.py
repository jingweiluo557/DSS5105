"""Path A: plain-python (csv + datetime) computation of every gold fact."""
import csv, datetime as dt, json
from collections import defaultdict

import os
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)   # run from anywhere; facts_*.json land beside the scripts
D = '../../../data/'
O = list(csv.DictReader(open(D + 'orders.csv')))
P = list(csv.DictReader(open(D + 'production_log.csv')))
W = list(csv.DictReader(open(D + 'workshops.csv')))
TODAY = dt.date(2026, 4, 1)
d = dt.date.fromisoformat
BYID = {o['order_id']: o for o in O}
ACT = [o for o in O if o['status'] == 'IN_PROGRESS']
STAGES = ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING']


def overdue(o):
    return o['status'] == 'IN_PROGRESS' and d(o['due_date']) < TODAY


def days_over(o):
    return (TODAY - d(o['due_date'])).days


def idle(o):
    return (TODAY - d(o['last_activity_date'])).days


def unique_max(items, key):
    best = max(key(x) for x in items)
    winners = [x for x in items if key(x) == best]
    return winners, best


def unique_min(items, key):
    best = min(key(x) for x in items)
    winners = [x for x in items if key(x) == best]
    return winners, best


LOG = {(p['date'], p['stage']): int(p['pieces_completed']) for p in P}


def prod(date, stage):
    return LOG.get((date, stage))


def normal(date, stage, value=None):
    dd = d(date)
    v = LOG[(date, stage)] if value is None else value
    hist = sorted((d(p['date']), int(p['pieces_completed'])) for p in P
                  if p['stage'] == stage and d(p['date']) < dd and d(p['date']).weekday() == dd.weekday())
    last8 = [x for _, x in hist[-8:]]
    assert len(last8) == 8
    lab = 'below' if v < min(last8) else 'above' if v > max(last8) else 'within'
    return (v, lab, min(last8), max(last8))


F = {}
# ---------- lookup
F['L01'] = (BYID['ORD-045']['current_stage'],)
F['L02'] = (BYID['ORD-062']['due_date'],)
F['L03'] = (BYID['ORD-107']['status'], BYID['ORD-107']['current_stage'], days_over(BYID['ORD-107']))
F['L04'] = (int(BYID['ORD-036']['pieces']),)
F['L05'] = (BYID['ORD-081']['current_stage'],)
F['L06'] = (BYID['ORD-057']['status'], BYID['ORD-057']['completed_date'])
F['L07'] = (BYID['ORD-099']['customer'], BYID['ORD-099']['due_date'])
F['L08'] = (BYID['ORD-008']['current_stage'],)
F['L09'] = (BYID['ORD-120']['due_date'], days_over(BYID['ORD-120']))
F['L10'] = (BYID['ORD-002']['last_activity_date'], idle(BYID['ORD-002']))
# ---------- aggregation
F['A01'] = (sum(1 for o in O if overdue(o)),)
F['A02'] = (sum(1 for o in ACT if o['current_stage'] == 'WASHING'),)
F['A03'] = (sum(int(o['pieces']) for o in ACT if o['customer'] == 'Harbor Knits'),)
F['A04'] = (sum(1 for o in ACT if o['customer'] == 'Loom & Leaf'),)
rng = [o for o in O if d('2026-04-11') <= d(o['due_date']) <= d('2026-04-19')]
# boundary-insensitivity check: nothing due exactly on 04-11 or 04-19
assert not any(o['due_date'] in ('2026-04-11', '2026-04-19') for o in O)
F['A05'] = (len(rng), tuple(sorted(o['order_id'] for o in rng)))
F['A06'] = (sum(1 for o in ACT if o['current_stage'] == 'KNITTING'),)
F['A07'] = (sum(int(o['pieces']) for o in ACT),)
F['A08'] = (sum(1 for o in O if o['status'] == 'COMPLETE' and o['completed_date'].startswith('2026-03')),)
F['A09'] = (sum(1 for o in O if overdue(o) and o['customer'] == 'Northwind Apparel'),)
F['A10'] = (sum(int(o['pieces']) for o in ACT if o['current_stage'] == 'ASSEMBLY'),
            sum(1 for o in ACT if o['current_stage'] == 'ASSEMBLY'))
# ---------- ranking
w, b = unique_max(ACT, idle); assert len(w) == 1; F['R01'] = (w[0]['order_id'], b, w[0]['last_activity_date'])
fut = [o for o in O if d(o['due_date']) > TODAY]
w, b = unique_min(fut, lambda o: d(o['due_date'])); assert len(w) == 1; F['R02'] = (w[0]['order_id'], str(b))
od = sorted([o for o in O if overdue(o)], key=lambda o: -days_over(o))
assert days_over(od[1]) > days_over(od[2])
F['R03'] = ((od[0]['order_id'], days_over(od[0])), (od[1]['order_id'], days_over(od[1])))
cp = defaultdict(int); cc = defaultdict(int)
for o in ACT:
    cp[o['customer']] += int(o['pieces']); cc[o['customer']] += 1
w, b = unique_max(list(cp), lambda c: cp[c]); assert len(w) == 1; F['R04'] = (w[0], b)
w, b = unique_min(list(cc), lambda c: cc[c]); assert len(w) == 1; F['R05'] = (w[0], b)
w, b = unique_min(ACT, lambda o: d(o['order_date'])); assert len(w) == 1; F['R06'] = (w[0]['order_id'], str(b))
wa = [o for o in ACT if o['current_stage'] == 'WASHING']
w, b = unique_min(wa, lambda o: d(o['due_date'])); assert len(w) == 1; F['R07'] = (w[0]['order_id'], str(b))
kn = [o for o in ACT if o['current_stage'] == 'KNITTING']
w, b = unique_max(kn, idle); assert len(w) == 1; F['R08'] = (w[0]['order_id'], b)
# ---------- comparison
def sooner(a, b_):
    x, y = BYID[a], BYID[b_]; assert x['due_date'] != y['due_date']
    return min((x['due_date'], a), (y['due_date'], b_))
def further(a, b_):
    x, y = BYID[a], BYID[b_]
    ia, ib = STAGES.index(x['current_stage']), STAGES.index(y['current_stage']); assert ia != ib
    return (a, x['current_stage']) if ia > ib else (b_, y['current_stage'])
F['C01'] = sooner('ORD-053', 'ORD-015')[::-1]
F['C02'] = further('ORD-062', 'ORD-103')
F['C03'] = max((int(BYID[i]['pieces']), i) for i in ('ORD-081', 'ORD-066'))[::-1]
F['C04'] = (max(('ORD-083', 'ORD-002'), key=lambda i: days_over(BYID[i])), days_over(BYID['ORD-083']), days_over(BYID['ORD-002']))
def nod(c): return sum(1 for o in O if overdue(o) and o['customer'] == c)
F['C05'] = (nod('Harbor Knits'), nod('Cotton Club'))
F['C06'] = sooner('ORD-099', 'ORD-103')[::-1]
F['C07'] = further('ORD-114', 'ORD-109')
F['C08'] = (nod('Maple & Co'), nod('Northwind Apparel'))
# ---------- production
F['P01'] = (prod('2026-03-28', 'PACKING'),)
F['P02'] = (d('2026-03-29').strftime('%A'), prod('2026-03-29', 'WASHING'))
F['P03'] = normal('2026-03-31', 'ASSEMBLY')
F['P04'] = normal('2026-03-13', 'KNITTING')
F['P05'] = normal('2026-03-09', 'WASHING')
F['P06'] = normal('2026-03-27', 'PACKING')
F['P07'] = normal('2026-03-31', 'KNITTING')
F['P08'] = normal('2026-03-20', 'WASHING')
F['P09'] = normal('2026-03-26', 'WASHING')
F['P10'] = normal('2026-04-01', 'KNITTING', value=1000)[1:]
# ---------- actions (facts = the order exists & is active; workshop exists)
WS = {w_['name']: w_ for w_ in W}
F['X01'] = (BYID['ORD-120']['status'], BYID['ORD-120']['current_stage'])
F['X02'] = (BYID['ORD-053']['status'], WS['QuickStitch']['workshop_id'], WS['QuickStitch']['status'])
F['X03'] = (BYID['ORD-083']['status'], BYID['ORD-083']['current_stage'])
F['X04'] = (BYID['ORD-045']['status'], WS['SteadyHands']['workshop_id'], WS['SteadyHands']['status'])
F['X05'] = (BYID['ORD-107']['customer'],)
F['X06'] = (sorted(o['order_id'] for o in ACT if o['customer'] == 'Cotton Club'),)
F['X07'] = (BYID['ORD-002']['status'],)
F['X08'] = (BYID['ORD-061']['current_stage'], d('2026-04-03').strftime('%A'))
# ---------- not on file
cust = {o['customer'] for o in O}; prods = {o['product'] for o in O}; wsn = {w_['name'] for w_ in W}
F['N01'] = ('ORD-150' in BYID,)
F['N02'] = ('ORD-121' in BYID,)
F['N03'] = ('Bluewater Textiles' in cust,)
F['N04'] = (any('sock' in p.lower() for p in prods),)
F['N05'] = (any(p['stage'] == 'DYEING' for p in P), 'DYEING' in {o['current_stage'] for o in O})
F['N06'] = (max(p['date'] for p in P), prod('2026-04-01', 'PACKING'))
F['N07'] = (any('silk' in n.lower() for n in wsn),)
F['N08'] = ('Patagonia' in cust,)
# ---------- multiturn (fact for each turn)
w, b = unique_max([o for o in O if overdue(o)], days_over); assert len(w) == 1
F['M01'] = (w[0]['order_id'], w[0]['customer'])
F['M02'] = (sooner('ORD-053', 'ORD-036')[1], BYID['ORD-036']['current_stage'])
cco = sorted(o['order_id'] for o in O if overdue(o) and o['customer'] == 'Cotton Club')
F['M03'] = (tuple(cco), sum(int(BYID[i]['pieces']) for i in cco))
idl = sorted(ACT, key=lambda o: -idle(o)); assert idle(idl[1]) > idle(idl[2])
F['M04'] = (idl[0]['order_id'], idl[1]['order_id'], idle(idl[1]))
F['M05'] = (BYID['ORD-061']['current_stage'], BYID['ORD-061']['due_date'])
tc = [o for o in ACT if o['customer'] == 'TrendCart']
w, b = unique_min(tc, lambda o: d(o['due_date'])); assert len(w) == 1
F['M06'] = (len(tc), w[0]['order_id'], str(b))
F['M07'] = normal('2026-03-25', 'ASSEMBLY')
F['M08'] = (BYID['ORD-029']['current_stage'], BYID['ORD-029']['due_date'], overdue(BYID['ORD-029']))


def norm(x):
    return json.loads(json.dumps(x, default=str))


if __name__ == '__main__':
    json.dump({k: norm(v) for k, v in F.items()}, open('facts_a.json', 'w'), indent=1)
    for k, v in F.items():
        print(k, v)
