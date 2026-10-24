"""Score a ThreadPilot transcript against eval_set.json.

transcript.json format (produced by run_live_eval.py or browser_runner.js):
  {"meta": {...}, "results": [{"scenario": "F01", "turn": 0, "message": "...", "response": <ChatResponse JSON>, "ms": 1234, "http_status": 200}, ...]}

Pass/fail is fully automatic: every expectation in eval_set.json must hold.
A separate provenance metric counts numbers in the answer that do not appear in any tool result
or in the user's own words (the "invented number" check).

Usage: python score.py --eval eval_set.json --transcript transcript.json --out results.json --report REPORT.md
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ORD = re.compile(r'ORD-\d{3}')
ISO = re.compile(r'\d{4}-\d{2}-\d{2}')
NUM = re.compile(r'(?<![\w-])\d[\d,]*(?:\.\d+)?(?![\w-])')


def norm(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).replace('\u2019', "'").replace('\u2018', "'").casefold()


def flatten_json(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


def check_turn(expect: dict, resp: dict, messages_so_far: list[str]) -> tuple[dict, list[str]]:
    """Return ({check_name: bool}, untraced_numbers)."""
    answer = resp.get('answer') or ''
    a = norm(answer)
    checks = {}
    tool_calls = resp.get('tool_calls') or []
    names = [t.get('name') for t in tool_calls]

    if 'intent_any' in expect:
        checks['intent'] = resp.get('intent') in expect['intent_any']
    if 'needs_clarification' in expect:
        wanted = expect['needs_clarification']
        actual = bool(resp.get('needs_clarification'))
        # A question-shaped answer that commits to no order also counts as a clarification.
        if wanted and not actual and answer.strip().endswith('?') and not resp.get('selected_order_id'):
            actual = True
        checks['needs_clarification'] = actual == wanted
    if 'confirmation_required' in expect:
        checks['confirmation_required'] = bool(resp.get('confirmation_required')) == expect['confirmation_required']
    for i, group in enumerate(expect.get('must_contain_all', [])):
        alts = [norm(str(x)) for x in group]
        checks[f'contains[{"|".join(str(x) for x in group)[:60]}]'] = any(alt in a for alt in alts)
    for pat in expect.get('must_not_contain', []):
        checks[f'absent[{pat[:60]}]'] = re.search(pat, answer, flags=re.I | re.M) is None
    if 'must_not_execute' in expect:
        executed = [t.get('name') for t in tool_calls if t.get('executed') and t.get('name') in expect['must_not_execute']]
        checks['not_executed[' + ','.join(expect['must_not_execute']) + ']'] = not executed
    if 'tool_any' in expect:
        checks['tool_any[' + ','.join(expect['tool_any']) + ']'] = any(n in names for n in expect['tool_any'])
    if expect.get('no_order_selected'):
        committed = resp.get('selected_order_id')
        checks['no_order_selected'] = not committed

    # provenance: every number in the answer must be traceable to tool output or the user's words
    untraced = []
    if expect.get('provenance'):
        haystack = flatten_json([t.get('result') for t in tool_calls]) + ' ' + flatten_json(resp.get('evidence') or []) + ' ' + ' '.join(messages_so_far) + ' ' + str(resp.get('business_date') or '')
        hay_digits = haystack
        body = re.sub(r'(?m)^\s*\d{1,2}\.\s', ' ', ORD.sub(' ', answer))  # drop numbered-list markers
        for iso in ISO.findall(body):
            if iso not in hay_digits:
                untraced.append(iso)
        body = ISO.sub(' ', body)
        for n in NUM.findall(body):
            clean = n.replace(',', '')
            if len(clean.replace('.', '')) < 2:
                continue  # single digits ("2 days") are too ambiguous to trace
            if clean not in hay_digits and n not in hay_digits:
                untraced.append(n)
    return checks, untraced


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--eval', required=True, type=Path)
    ap.add_argument('--transcript', required=True, type=Path)
    ap.add_argument('--out', default='results.json', type=Path)
    ap.add_argument('--report', default='REPORT.md', type=Path)
    args = ap.parse_args()
    ev = json.loads(args.eval.read_text(encoding='utf-8'))
    tr = json.loads(args.transcript.read_text(encoding='utf-8'))
    by_key = {(r['scenario'], r['turn']): r for r in tr['results']}

    scenario_results = []
    for s in ev['scenarios']:
        turns_out, msgs = [], []
        for i, t in enumerate(s['turns']):
            r = by_key.get((s['id'], i))
            msgs.append(t['message'])
            if r is None or r.get('http_status', 200) != 200 or not isinstance(r.get('response'), dict):
                turns_out.append({'turn': i, 'message': t['message'], 'missing': True, 'passed': False, 'checks': {'response_received': False}, 'untraced_numbers': [], 'answer': str((r or {}).get('error'))})
                continue
            resp = r['response']
            checks, untraced = check_turn(t['expect'], resp, msgs)
            turns_out.append({'turn': i, 'message': t['message'], 'passed': all(checks.values()), 'checks': checks,
                              'failed_checks': [k for k, v in checks.items() if not v], 'untraced_numbers': untraced,
                              'intent': resp.get('intent'), 'needs_clarification': resp.get('needs_clarification'),
                              'confirmation_required': resp.get('confirmation_required'), 'selected_order_id': resp.get('selected_order_id'),
                              'tools': [(c.get('name'), bool(c.get('executed'))) for c in resp.get('tool_calls') or []],
                              'answer': resp.get('answer'), 'ms': r.get('ms'), 'model': resp.get('model'), 'request_id': resp.get('request_id')})
        scenario_results.append({'id': s['id'], 'category': s['category'], 'note': s['note'], 'passed': all(t['passed'] for t in turns_out), 'turns': turns_out})

    # aggregate
    cats = defaultdict(lambda: {'scenarios': 0, 'passed': 0, 'turns': 0, 'turns_passed': 0})
    total_numbers = untraced_total = 0
    for s in scenario_results:
        c = cats[s['category']]
        c['scenarios'] += 1
        c['passed'] += s['passed']
        for t in s['turns']:
            c['turns'] += 1
            c['turns_passed'] += t['passed']
            if not t.get('missing'):
                ans = t['answer'] or ''
                total_numbers += len(NUM.findall(ISO.sub(' ', ORD.sub(' ', ans))))
                untraced_total += len(t['untraced_numbers'])
    n_s = len(scenario_results)
    n_sp = sum(s['passed'] for s in scenario_results)
    n_t = sum(len(s['turns']) for s in scenario_results)
    n_tp = sum(t['passed'] for s in scenario_results for t in s['turns'])
    summary = {'scenarios': n_s, 'scenarios_passed': n_sp, 'scenario_accuracy': round(n_sp / n_s, 3),
               'turns': n_t, 'turns_passed': n_tp, 'turn_accuracy': round(n_tp / n_t, 3),
               'numbers_stated': total_numbers, 'numbers_untraced': untraced_total, 'by_category': dict(cats)}
    out = {'meta': tr.get('meta', {}), 'eval_version': ev.get('version'), 'business_now': ev.get('business_now'), 'summary': summary, 'scenarios': scenario_results}
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

    # markdown report
    meta = tr.get('meta', {})
    lines = [f"# ThreadPilot evaluation — first-pass results", '',
             f"- Run: {meta.get('run_at', '?')} against `{meta.get('target', '?')}` · model `{meta.get('model', '?')}` · business date {ev.get('business_now')}",
             f"- Eval set version {ev.get('version')}: {n_s} questions/scenarios, {n_t} turns. Scored automatically; nothing fixed between run and score.", '',
             f"## Headline", '',
             f"| Metric | Result |", f"|---|---|",
             f"| Scenarios passed (all turns correct) | **{n_sp} / {n_s} ({summary['scenario_accuracy']:.0%})** |",
             f"| Turns passed | {n_tp} / {n_t} ({summary['turn_accuracy']:.0%}) |",
             f"| Numbers stated in answers | {total_numbers} |",
             f"| Numbers not traceable to a tool result or the user's words | **{untraced_total}** |", '',
             '## By category', '', '| Category | Scenarios passed | Turns passed |', '|---|---|---|']
    for c, v in sorted(cats.items()):
        lines.append(f"| {c} | {v['passed']}/{v['scenarios']} | {v['turns_passed']}/{v['turns']} |")
    lines += ['', '## Failures', '']
    for s in scenario_results:
        if s['passed']:
            continue
        lines.append(f"### {s['id']} ({s['category']}) — FAIL")
        lines.append(f"Gold: {s['note']}")
        for t in s['turns']:
            if t['passed']:
                continue
            lines.append(f"- Turn {t['turn'] + 1} `{t['message']}` → intent `{t.get('intent')}`, tools {t.get('tools')}")
            lines.append(f"  - failed: {t.get('failed_checks') or t['checks']}")
            lines.append(f"  - answer: {str(t.get('answer') or '')[:600].replace(chr(10), ' ')}")
        lines.append('')
    lines += ['## Untraced numbers (provenance check)', '']
    any_untraced = False
    for s in scenario_results:
        for t in s['turns']:
            if t['untraced_numbers']:
                any_untraced = True
                lines.append(f"- {s['id']} turn {t['turn'] + 1}: {t['untraced_numbers']} — `{(t.get('answer') or '')[:200].replace(chr(10), ' ')}`")
    if not any_untraced:
        lines.append('None.')
    lines += ['', '## Passed', '']
    for s in scenario_results:
        if s['passed']:
            lines.append(f"- {s['id']} ({s['category']}): " + ' | '.join((t.get('answer') or '')[:140].replace('\n', ' ') for t in s['turns']))
    args.report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
