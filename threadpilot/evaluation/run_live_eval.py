"""Run eval_set.json against a live ThreadPilot backend over HTTP and write transcript.json.

Each scenario is a fresh session (session_id=null on its first turn). The confirmation_id returned by
one turn is passed back on the next turn, exactly as frontend/ai-stream.js does.

Usage:
  THREADPILOT_TOKEN=<workspace access key> python run_live_eval.py \
      --base https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com \
      --eval eval_set.json --out transcript.json [--only F01,M01] [--sleep 1.0]

Then:  python score.py --eval eval_set.json --transcript transcript.json
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error


def post(base: str, token: str, body: dict, timeout: int = 120):
    req = request.Request(base.rstrip('/') + '/api/v1/workflow/chat', data=json.dumps(body).encode('utf-8'), method='POST',
                          headers={'Content-Type': 'application/json', 'X-ThreadPilot-Token': token})
    t0 = time.time()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return resp.status, data, int((time.time() - t0) * 1000)
    except error.HTTPError as e:
        try:
            data = json.loads(e.read().decode('utf-8'))
        except Exception:
            data = {'error': str(e)}
        return e.code, data, int((time.time() - t0) * 1000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--eval', default='eval_set.json', type=Path)
    ap.add_argument('--out', default='transcript.json', type=Path)
    ap.add_argument('--only', default='')
    ap.add_argument('--sleep', type=float, default=1.0)
    args = ap.parse_args()
    token = os.environ.get('THREADPILOT_TOKEN')
    if not token:
        raise SystemExit('Set THREADPILOT_TOKEN to the workspace access key (never commit it).')
    ev = json.loads(args.eval.read_text(encoding='utf-8'))
    only = {x for x in args.only.split(',') if x}
    results, model = [], None
    for s in ev['scenarios']:
        if only and s['id'] not in only:
            continue
        session, confirmation = None, None
        for i, t in enumerate(s['turns']):
            status, data, ms = post(args.base, token, {'message': t['message'], 'session_id': session, 'confirmation_id': confirmation})
            item = {'scenario': s['id'], 'turn': i, 'message': t['message'], 'http_status': status, 'ms': ms}
            if status == 200:
                item['response'] = data
                session = (data.get('state') or {}).get('session_id') or session
                confirmation = data.get('confirmation_id')
                model = data.get('model') or model
                print(f"{s['id']}.{i + 1} {ms:5d}ms {data.get('intent'):<22} {str(data.get('answer'))[:110]!r}")
            else:
                item['error'] = data
                print(f"{s['id']}.{i + 1} HTTP {status}: {str(data)[:200]}")
            results.append(item)
            time.sleep(args.sleep)
        args.out.write_text(json.dumps({'meta': {'run_at': datetime.now(timezone.utc).isoformat(), 'target': args.base, 'model': model, 'first_pass': True}, 'results': results}, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'wrote {args.out} ({len(results)} turns)')


if __name__ == '__main__':
    main()
