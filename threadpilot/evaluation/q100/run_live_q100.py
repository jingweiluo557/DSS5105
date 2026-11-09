"""Run the 100-question × 3-context sheet against a live ThreadPilot backend (the real planner model) and write
answers_live.json in the shape grade.py reads.  One session per Scenario per context, confirmation_id carried like the frontend.

  THREADPILOT_TOKEN=<workspace access key> python run_live_q100.py --base https://<backend> [--ctx 1,2,3] [--sleep 1]
  python grade.py answers_live.json

The token is read from the environment only; never put it on the command line or in a file that is committed."""
from __future__ import annotations
import argparse, json, os, re, time
from pathlib import Path
from urllib import request, error

HERE = Path(__file__).resolve().parent
SET = os.environ.get('Q100_SET', 'q100')   # similar = the 'Similar Questions' tab (grade with grade_similar.py)
Q = json.loads((HERE / ('questions.json' if SET == 'q100' else f'{SET}_questions.json')).read_text(encoding='utf-8'))


def post(base, token, body, timeout=120):
    req = request.Request(base.rstrip('/') + '/api/v1/workflow/chat', data=json.dumps(body).encode('utf-8'), method='POST',
                          headers={'Content-Type': 'application/json', 'X-ThreadPilot-Token': token})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode('utf-8'))
        except Exception: return e.code, {'error': str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--ctx', default='1,2,3')
    ap.add_argument('--sleep', type=float, default=1.0)
    ap.add_argument('--out', default=str(HERE / ('answers_live.json' if SET == 'q100' else f'answers_{SET}_live.json')))
    args = ap.parse_args()
    token = os.environ.get('THREADPILOT_TOKEN')
    if not token:
        raise SystemExit('Set THREADPILOT_TOKEN to the workspace access key (never commit it).')
    groups = {}
    for q in Q: groups.setdefault(q['scenario'], []).append(q)
    out = []
    for ctx in [int(c) for c in args.ctx.split(',')]:
        for scenario, rows in groups.items():
            session, conf = None, None
            for q in rows:
                msg = q['q'][ctx - 1]
                if not msg: continue
                turns = []
                status, data = post(args.base, token, {'message': msg, 'session_id': session, 'confirmation_id': conf})
                if status != 200:
                    out.append(dict(no=q['no'], ctx=ctx, field=q['field'], q=msg, error=f'HTTP {status}: {data}', turns=turns, answer=''))
                    time.sleep(args.sleep); continue
                session, conf = (data.get('state') or {}).get('session_id', session), data.get('confirmation_id')
                turns.append((msg, data.get('answer', '')))
                for _ in range(2):   # the product's standard one-question clarifications, answered as a user would
                    a = data.get('answer') or ''
                    if data.get('needs_clarification') and 'ready at our factory or delivered' in a: follow = 'Ready at the factory.'
                    elif data.get('needs_clarification') and 'Due today only, or include the next seven days' in a: follow = 'Include the next seven days.'
                    else: break
                    time.sleep(args.sleep)
                    status, data = post(args.base, token, {'message': follow, 'session_id': session, 'confirmation_id': conf})
                    conf = data.get('confirmation_id'); turns.append((follow, data.get('answer', '')))
                sent = sum(1 for c in data.get('tool_calls', []) if c.get('name') == 'send_chase' and c.get('executed'))
                out.append(dict(no=q['no'], ctx=ctx, field=q['field'], q=msg, normalized=msg, intent=str(data.get('intent')), clar=bool(data.get('needs_clarification')),
                                confreq=bool(data.get('confirmation_required')), selected=data.get('selected_order_id'), tools=[c.get('name') for c in data.get('tool_calls', [])],
                                sent=sent, turns=turns, answer=data.get('answer', ''), model=data.get('model')))
                print(f"{q['no']}.{ctx} {msg[:50]!r} -> {str(data.get('answer',''))[:70]!r}")
                time.sleep(args.sleep)
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{len(out)} answers -> {args.out}; now: python ' + ('grade.py' if SET == 'q100' else 'grade_similar.py') + f' {args.out}')


if __name__ == '__main__':
    main()
