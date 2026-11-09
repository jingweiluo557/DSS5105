"""Run the 70 held-out questions against the deployed ThreadPilot (the real planner model) and grade them with the same
rules as run_heldout.py. This is the end-to-end number the offline run cannot give: it includes the model's own reading.

  THREADPILOT_TOKEN=<workspace access key> python run_live_heldout.py --base https://<backend>
  -> results/heldout_live.json + a per-category table

The token is read from the environment only; never put it on the command line or in a committed file. Each item gets a
fresh chat session; for multi-turn items only the last answer is graded. Nothing is sent: chase-ups stop at the preview
because the runner never confirms. Business date: the deployed snapshot's (2026-04-01 for the Track 1 data).
"""
import argparse, json, os, sys, time
from pathlib import Path
from urllib import error, request

HERE = Path(__file__).resolve().parent
ITEMS = json.loads((HERE / 'heldout.json').read_text(encoding='utf-8'))


def load_grader():
    """grade() and table() from run_heldout.py, without importing the offline engine."""
    src = (HERE / 'run_heldout.py').read_text(encoding='utf-8')
    ns = {'__name__': 'grader'}
    import re
    exec(compile('import json, re\n' + src[src.index('SEND_WORDS'):src.index('# Manual audit')], 'run_heldout_grade', 'exec'), ns)
    exec(compile(src[src.index('def table'):src.index("if __name__")], 'run_heldout_table', 'exec'), ns)
    return ns['grade'], ns['table']


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
    ap.add_argument('--base', required=True, help='the backend origin, e.g. https://dss5105-track1-….app.tcloudbase.com')
    ap.add_argument('--sleep', type=float, default=1.0)
    args = ap.parse_args()
    token = os.environ.get('THREADPILOT_TOKEN')
    if not token:
        raise SystemExit('Set THREADPILOT_TOKEN to the workspace access key (never commit it).')
    grade, table = load_grader()
    out = []
    for item in ITEMS:
        session, resp, err = None, None, None
        for turn in item['turns']:
            status, data = post(args.base, token, {'message': turn, 'session_id': session})
            if status != 200:
                err = f'HTTP {status}: {str(data)[:200]}'; break
            resp = data; session = (data.get('state') or {}).get('session_id', session)
            time.sleep(args.sleep)
        sent = sum(1 for c in (resp or {}).get('tool_calls', []) if c.get('name') == 'send_chase' and c.get('executed'))
        r = dict(id=item['id'], category=item['category'], turns=item['turns'], gold=item['gold']['answer_text'], error=err,
                 answer=(resp or {}).get('answer', '') if not err else '', intent=str((resp or {}).get('intent')),
                 clar=bool((resp or {}).get('needs_clarification')), confreq=bool((resp or {}).get('confirmation_required')),
                 sent=sent, model=(resp or {}).get('model'))
        r['verdict'], r['why'] = grade(item, r)
        out.append(r)
        print(f"{item['id']} {r['verdict']:7s} {item['turns'][-1][:50]!r} -> {r['answer'][:70]!r}", flush=True)
    (HERE / 'results').mkdir(exist_ok=True)
    (HERE / 'results' / 'heldout_live.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print('live model (automatic grade; audit the non-PASS rows by hand as in run_heldout.py before reporting):')
    table(out)


if __name__ == '__main__':
    main()
