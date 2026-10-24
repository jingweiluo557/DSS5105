"""Cross-check the deterministic tool results captured in a live transcript against the independently computed gold values.

This is the 'did the tools compute the right thing' check, separate from 'did the model narrate the tool correctly'.
Usage: python verify_tool_results.py --eval eval_set.json --transcript transcript.json
"""
import argparse, json
from pathlib import Path

ap = argparse.ArgumentParser(); ap.add_argument('--eval', type=Path, default='eval_set.json'); ap.add_argument('--transcript', type=Path, required=True)
a = ap.parse_args()
ev = json.loads(a.eval.read_text(encoding='utf-8')); tr = json.loads(a.transcript.read_text(encoding='utf-8'))
G = ev['gold']; checks = []

def tool(sid, turn, name):
    for r in tr['results']:
        if r['scenario'] == sid and r['turn'] == turn and r.get('response'):
            for t in r['response'].get('tool_calls', []):
                if t['name'] == name:
                    return t['result']
    return None

def cmp(label, got, want):
    checks.append((label, got == want, got, want))

r = tool('F01', 0, 'summarize_orders');            cmp('summarize_orders.by_status.IN_PROGRESS', r and r['by_status'].get('IN_PROGRESS'), G['facts']['n_in_progress'])
r = tool('F07', 0, 'summarize_orders');            cmp('summarize_orders(customer=TrendCart).by_status.IN_PROGRESS', r and r['by_status'].get('IN_PROGRESS'), len(G['facts']['active_by_customer']['TrendCart']))
import re
r = tool('F10', 0, 'prioritize_orders')
ids = [o['order_id'] for o in r['orders']] if isinstance(r, dict) and 'orders' in r else list(dict.fromkeys(re.findall(r'"order_id":"(ORD-\d{3})"', (r or {}).get('head', '')))) if r else None
want = G['facts']['due_within_7_incl_overdue']
cmp('prioritize_orders(7d) order list (prefix if transcript truncated)', ids[:len(want)] if ids else None, want[:len(ids)] if ids else want)
r = tool('J03', 0, 'check_normality');             n = G['normality']['PACKING_yesterday']; cmp('check_normality PACKING yesterday (min,max,mean,output,status)', r and (r['minimum'], r['maximum'], r['mean'], r['output'], r['status']), (n['minimum'], n['maximum'], n['mean'], n['output'], n['status']))
r = tool('J01b', 1, 'check_normality');            n = G['normality']['ASSEMBLY_yesterday']; cmp('check_normality ASSEMBLY yesterday (min,max,mean,output,status)', r and (r['minimum'], r['maximum'], r['mean'], r['output'], r['status']), (n['minimum'], n['maximum'], n['mean'], n['output'], n['status']))
INFEASIBLE = {'not supported by conservative estimate', 'unlikely by this date', 'unlikely'}
r = tool('Fe01', 1, 'estimate_capacity');          c = G['capacity']['hoodies_800_apr25_customer']; cmp('estimate_capacity 800 hoodies->customer by 25 Apr (available, worst-case required, limiting, infeasible verdict)', r and (r['available_workdays'], r['scenario_required_days'], r['limiting_stage'], r['preliminary'] in INFEASIBLE), (c['available_workdays'], c['scenario_required_days'], c['limiting_stage'], c['preliminary'] in INFEASIBLE))
r = tool('Fe01', 3, 'estimate_capacity');          c = G['capacity']['hoodies_800_apr25_customer_loss1']; cmp('estimate_capacity + 1 lost packing day (required, slack)', r and (r['scenario_required_days'], r['buffer_days_remaining']), (c['scenario_required_days'], c['buffer_days_remaining']))
r = tool('Fe02', 0, 'estimate_capacity');          c = G['capacity']['beanies_300_apr15_customer']; cmp('estimate_capacity 300 beanies->customer by 15 Apr', r and (r['available_workdays'], r['scenario_required_days'], r['limiting_stage']), (c['available_workdays'], c['scenario_required_days'], c['limiting_stage']))
r = tool('T02', 0, 'assess_order_risk');           o = G['facts']['ORD-002']; cmp('assess_order_risk ORD-002 (idle_days, days_to_due, overdue)', r and (r['idle_days'], r['days_to_due'], r['overdue']), (o['idle_days'], o['days_to_due'], True))
r = tool('M03', 0, 'refresh_order');               o = G['facts']['ORD-053']; cmp('refresh_order ORD-053 record', r and {k: r.get(k) for k in ('customer', 'product', 'pieces', 'current_stage', 'due_date', 'last_activity_date')} if isinstance(r, dict) else None, {k: o[k] for k in ('customer', 'product', 'pieces', 'current_stage', 'due_date', 'last_activity_date')})
r = tool('U04', 0, 'explain_deviation');           n = G['normality']['ASSEMBLY_2026-03-25']; cmp('explain_deviation ASSEMBLY 2026-03-25 comparison (min,max,output)', r and (r['comparison']['minimum'], r['comparison']['maximum'], r['comparison']['output']), (n['minimum'], n['maximum'], n['output']))

ok = sum(1 for c in checks if c[1])
for label, passed, got, want in checks:
    print(('OK   ' if passed else 'DIFF ') + label + ('' if passed else f'\n      got  {got}\n      want {want}'))
print(f'\n{ok}/{len(checks)} deterministic tool results match the independent gold computation')
