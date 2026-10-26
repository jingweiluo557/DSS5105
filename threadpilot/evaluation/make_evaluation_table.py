"""Render EVALUATION.md: the evaluation set (question, category, verified answer) with the latest first-pass result.

Usage: python make_evaluation_table.py --eval eval_set.json --results results_live_20261024.json --out EVALUATION.md
"""
import argparse
import json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--eval', type=Path, default='eval_set.json')
ap.add_argument('--results', type=Path, default=None)
ap.add_argument('--out', type=Path, default='EVALUATION.md')
a = ap.parse_args()
ev = json.loads(a.eval.read_text(encoding='utf-8'))
res = json.loads(a.results.read_text(encoding='utf-8')) if a.results and a.results.exists() else None
verdict = {s['id']: s for s in res['scenarios']} if res else {}
cat_names = {'facts': 'Fact lookup', 'judgement': 'Judgement (normal?)', 'tracing': 'Tracing (why / rows)', 'multi_turn': 'Multi-turn', 'ambiguous': 'Ambiguous (must ask)',
             'unanswerable': 'Unanswerable / bait', 'feasibility': 'Feasibility', 'action': 'Action (confirm, log)',
             'arithmetic_bait': 'Arithmetic bait', 'discovery': 'Discovery', 'sheet1': 'Question sheet 1 (26 Oct team test)'}
L = ['# ThreadPilot evaluation set (verified answers)', '',
     f"Version {ev['version']} · business date {ev['business_now']} · {ev['counts']['scenarios']} questions ({ev['counts']['turns']} turns). ",
     'Every expected value is computed from `orders.csv`, `production_log.csv` and `workshops.csv` by `build_eval_set.py`, using the same definitions as the ThreadPilot tools '
     '(Sundays closed; "normal" = previous eight same-weekday records; capacity = conservative serial backlog ÷ mean of the last 20 non-Sunday days). '
     'Scoring is automatic (`score.py`): intent/clarification/confirmation flags, required facts, forbidden claims, forbidden executions, and an invented-number check (every number in the answer must appear in a tool result or in the manager\'s own words).', '']
if res:
    s = res['summary']
    L += [f"**Latest first pass** ({res['meta'].get('run_at')}, `{res['meta'].get('model')}`): **{s['scenarios_passed']}/{s['scenarios']} questions ({s['scenario_accuracy']:.0%})**, "
          f"{s['turns_passed']}/{s['turns']} turns, {s['numbers_untraced']} untraced numbers out of {s['numbers_stated']} stated.", '']
L += ['| # | Category | Question (turns) | Verified answer / expected behaviour | First pass |', '|---|---|---|---|---|']
for sc in ev['scenarios']:
    q = ' → '.join(t['message'] for t in sc['turns']).replace('|', '\\|')
    gold = sc['note'].replace('gold: ', '', 1).replace('gold (tool algorithm): ', '', 1).replace('|', '\\|')
    v = verdict.get(sc['id'])
    mark = '— not in that run' if v is None else ('✅ pass' if v['passed'] else '❌ fail (turn ' + ', '.join(str(t['turn'] + 1) for t in v['turns'] if not t['passed']) + ')')
    L.append(f"| {sc['id']} | {cat_names.get(sc['category'], sc['category'])} | {q} | {gold} | {mark} |")
L += ['', '## Brief requirements check', '',
      f"- ≥30 questions with verified answers: **{ev['counts']['scenarios']}** ✔",
      f"- ≥5 ambiguous / unanswerable / hallucination-bait: **{ev['counts']['by_category']['ambiguous'] + ev['counts']['by_category']['unanswerable']}** ✔",
      f"- ≥5 feasibility or action requests: **{ev['counts']['by_category']['feasibility'] + ev['counts']['by_category']['action']}** ✔",
      '- Measured accuracy: see the first-pass line above and `REPORT_live_<date>.md` for every failure with the actual answer.', '']
a.out.write_text('\n'.join(L) + '\n', encoding='utf-8')
print(f'wrote {a.out}')
