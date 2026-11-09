"""Path B: independent re-computation via SQLite SQL (julianday / strftime), no shared code with path A."""
import csv, sqlite3, json

import os
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)   # run from anywhere; facts_*.json land beside the scripts
D = '../../../data/'
db = sqlite3.connect(':memory:')
for name in ('orders', 'production_log', 'workshops'):
    rows = list(csv.reader(open(D + name + '.csv')))
    db.execute(f'create table {name} ({",".join(rows[0])})')
    db.executemany(f'insert into {name} values ({",".join("?" * len(rows[0]))})', rows[1:])
q = lambda s, *a: db.execute(s, a).fetchall()
one = lambda s, *a: q(s, *a)[0]
T = "'2026-04-01'"
ACT = "status='IN_PROGRESS'"
OVD = f"status='IN_PROGRESS' and due_date < {T}"
DO = f"cast(julianday({T})-julianday(due_date) as int)"
ID = f"cast(julianday({T})-julianday(last_activity_date) as int)"
RANK = "case current_stage when 'KNITTING' then 1 when 'ASSEMBLY' then 2 when 'WASHING' then 3 when 'PACKING' then 4 end"

def col(c, oid): return one(f'select {c} from orders where order_id=?', oid)[0]

def norm(date, stage, value=None):
    v = value if value is not None else int(one('select pieces_completed from production_log where date=? and stage=?', date, stage)[0])
    h = [int(r[0]) for r in q("""select pieces_completed from production_log
            where stage=? and date<? and strftime('%w',date)=strftime('%w',?) order by date desc limit 8""", stage, date, date)]
    assert len(h) == 8
    lo, hi = min(h), max(h)
    return [v, 'below' if v < lo else ('above' if v > hi else 'within'), lo, hi]

def top(sql, n=1):
    r = q(sql)
    if n == 1: assert r[0][1] != r[1][1], ('tie', r[:3])
    return r

F = {}
F['L01'] = [col('current_stage', 'ORD-045')]
F['L02'] = [col('due_date', 'ORD-062')]
F['L03'] = list(one(f'select status,current_stage,{DO} from orders where order_id="ORD-107"'))
F['L04'] = [int(col('pieces', 'ORD-036'))]
F['L05'] = [col('current_stage', 'ORD-081')]
F['L06'] = list(one('select status,completed_date from orders where order_id="ORD-057"'))
F['L07'] = list(one('select customer,due_date from orders where order_id="ORD-099"'))
F['L08'] = [col('current_stage', 'ORD-008')]
F['L09'] = list(one(f'select due_date,{DO} from orders where order_id="ORD-120"'))
F['L10'] = list(one(f'select last_activity_date,{ID} from orders where order_id="ORD-002"'))

F['A01'] = [one(f'select count(*) from orders where {OVD}')[0]]
F['A02'] = [one(f"select count(*) from orders where {ACT} and current_stage='WASHING'")[0]]
F['A03'] = [one(f"select sum(pieces) from orders where {ACT} and customer='Harbor Knits'")[0]]
F['A04'] = [one(f"select count(*) from orders where {ACT} and customer='Loom & Leaf'")[0]]
ids = [r[0] for r in q("select order_id from orders where due_date between '2026-04-11' and '2026-04-19' order by order_id")]
ids_strict = [r[0] for r in q("select order_id from orders where due_date > '2026-04-11' and due_date < '2026-04-19' order by order_id")]
assert ids == ids_strict
F['A05'] = [len(ids), ids]
F['A06'] = [one(f"select count(*) from orders where {ACT} and current_stage='KNITTING'")[0]]
F['A07'] = [one(f"select sum(pieces) from orders where {ACT}")[0]]
F['A08'] = [one("select count(*) from orders where status='COMPLETE' and completed_date between '2026-03-01' and '2026-03-31'")[0]]
F['A09'] = [one(f"select count(*) from orders where {OVD} and customer='Northwind Apparel'")[0]]
F['A10'] = list(one(f"select sum(pieces),count(*) from orders where {ACT} and current_stage='ASSEMBLY'"))

r = top(f'select order_id,{ID},last_activity_date from orders where {ACT} order by 2 desc'); F['R01'] = list(r[0])
r = top(f"select order_id,due_date from orders where due_date>{T} order by due_date"); F['R02'] = list(r[0])
r = q(f'select order_id,{DO} from orders where {OVD} order by 2 desc'); assert r[1][1] > r[2][1]; F['R03'] = [list(r[0]), list(r[1])]
r = top(f'select customer,sum(pieces) s from orders where {ACT} group by customer order by s desc'); F['R04'] = list(r[0])
r = top(f'select customer,count(*) c from orders where {ACT} group by customer order by c asc'); F['R05'] = list(r[0])
r = top(f'select order_id,order_date from orders where {ACT} order by order_date'); F['R06'] = list(r[0])
r = top(f"select order_id,due_date from orders where {ACT} and current_stage='WASHING' order by due_date"); F['R07'] = list(r[0])
r = top(f"select order_id,{ID} from orders where {ACT} and current_stage='KNITTING' order by 2 desc"); F['R08'] = list(r[0])

def cmp(a, b, expr, desc):
    r = q(f"select order_id,{expr} from orders where order_id in (?,?) order by 2 {'desc' if desc else 'asc'}", a, b)
    assert r[0][1] != r[1][1]; return list(r[0])
F['C01'] = cmp('ORD-053', 'ORD-015', 'due_date', False)
r = cmp('ORD-062', 'ORD-103', RANK, True); F['C02'] = [r[0], col('current_stage', r[0])]
r = cmp('ORD-081', 'ORD-066', 'cast(pieces as int)', True); F['C03'] = r
F['C04'] = [cmp('ORD-083', 'ORD-002', DO, True)[0], one(f'select {DO} from orders where order_id="ORD-083"')[0], one(f'select {DO} from orders where order_id="ORD-002"')[0]]
cnt = lambda c: one(f'select count(*) from orders where {OVD} and customer=?', c)[0]
F['C05'] = [cnt('Harbor Knits'), cnt('Cotton Club')]
F['C06'] = cmp('ORD-099', 'ORD-103', 'due_date', False)
r = cmp('ORD-114', 'ORD-109', RANK, True); F['C07'] = [r[0], col('current_stage', r[0])]
F['C08'] = [cnt('Maple & Co'), cnt('Northwind Apparel')]

pc = lambda dt_, s: (q('select cast(pieces_completed as int) from production_log where date=? and stage=?', dt_, s) or [[None]])[0][0]
F['P01'] = [pc('2026-03-28', 'PACKING')]
dow = one("select strftime('%w','2026-03-29')")[0]
F['P02'] = [{'0': 'Sunday'}.get(dow, dow), pc('2026-03-29', 'WASHING')]
F['P03'] = norm('2026-03-31', 'ASSEMBLY')
F['P04'] = norm('2026-03-13', 'KNITTING')
F['P05'] = norm('2026-03-09', 'WASHING')
F['P06'] = norm('2026-03-27', 'PACKING')
F['P07'] = norm('2026-03-31', 'KNITTING')
F['P08'] = norm('2026-03-20', 'WASHING')
F['P09'] = norm('2026-03-26', 'WASHING')
F['P10'] = norm('2026-04-01', 'KNITTING', 1000)[1:]

F['X01'] = list(one('select status,current_stage from orders where order_id="ORD-120"'))
F['X02'] = [col('status', 'ORD-053')] + list(one("select workshop_id,status from workshops where name='QuickStitch'"))
F['X03'] = list(one('select status,current_stage from orders where order_id="ORD-083"'))
F['X04'] = [col('status', 'ORD-045')] + list(one("select workshop_id,status from workshops where name='SteadyHands'"))
F['X05'] = [col('customer', 'ORD-107')]
F['X06'] = [[r[0] for r in q(f"select order_id from orders where {ACT} and customer='Cotton Club' order by order_id")]]
F['X07'] = [col('status', 'ORD-002')]
F['X08'] = [col('current_stage', 'ORD-061'), {'5': 'Friday'}[one("select strftime('%w','2026-04-03')")[0]]]

ex = lambda s, *a: bool(one(s, *a)[0])
F['N01'] = [ex("select count(*) from orders where order_id='ORD-150'")]
F['N02'] = [ex("select count(*) from orders where order_id='ORD-121'")]
F['N03'] = [ex("select count(*) from orders where customer like '%Bluewater%'")]
F['N04'] = [ex("select count(*) from orders where product like '%sock%'")]
F['N05'] = [ex("select count(*) from production_log where upper(stage) like '%DYE%'"), ex("select count(*) from orders where upper(current_stage) like '%DYE%'")]
F['N06'] = [one('select max(date) from production_log')[0], pc('2026-04-01', 'PACKING')]
F['N07'] = [ex("select count(*) from workshops where lower(name) like '%silk%'")]
F['N08'] = [ex("select count(*) from orders where customer like '%Patagonia%'")]

r = top(f'select order_id,{DO},customer from orders where {OVD} order by 2 desc'); F['M01'] = [r[0][0], r[0][2]]
F['M02'] = [cmp('ORD-053', 'ORD-036', 'due_date', False)[0], col('current_stage', 'ORD-036')]
r = q(f"select order_id,pieces from orders where {OVD} and customer='Cotton Club' order by order_id")
F['M03'] = [[x[0] for x in r], sum(int(x[1]) for x in r)]
r = q(f'select order_id,{ID} from orders where {ACT} order by 2 desc limit 3'); assert r[1][1] > r[2][1] and r[0][1] > r[1][1]
F['M04'] = [r[0][0], r[1][0], r[1][1]]
F['M05'] = list(one('select current_stage,due_date from orders where order_id="ORD-061"'))
n = one(f"select count(*) from orders where {ACT} and customer='TrendCart'")[0]
r = top(f"select order_id,due_date from orders where {ACT} and customer='TrendCart' order by due_date")
F['M06'] = [n, r[0][0], r[0][1]]
F['M07'] = norm('2026-03-25', 'ASSEMBLY')
F['M08'] = list(one(f'select current_stage,due_date,due_date<{T} from orders where order_id="ORD-029"'))
F['M08'][2] = bool(F['M08'][2])

if __name__ == '__main__':
    json.dump(F, open('facts_b.json', 'w'), indent=1)
    A = json.load(open('facts_a.json'))
    bad = [k for k in A if json.dumps(A[k]) != json.dumps(json.loads(json.dumps(F.get(k))))]
    missing = set(A) ^ set(F)
    print('compared', len(A), 'mismatches', bad, 'missing', missing)
    for k in bad: print(k, A[k], F.get(k))
