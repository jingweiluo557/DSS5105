"""Emit JavaScript snippets that run eval scenarios from inside the signed-in ThreadPilot page.

The page's own window.threadpilotFetch attaches the workspace token, so the token never leaves the browser.
Results accumulate in window.__tp_eval; each snippet returns a compact progress summary.
A final snippet (dump.js) returns the stored transcript as JSON text, chunked.

Usage: python make_browser_batches.py --eval eval_set.json --outdir browser_batches --per-batch 4
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RUNNER = r"""
window.__tp_eval = window.__tp_eval || {};
const base = window.THREADPILOT_API_BASE;
const scenarios = %SCENARIOS%;
const out = [];
for (const s of scenarios) {
  let session = null, confirmation = null;
  window.__tp_eval[s.id] = [];
  for (let i = 0; i < s.turns.length; i++) {
    const t0 = Date.now();
    let status = 0, data = null, err = null;
    try {
      const r = await window.threadpilotFetch(base + '/api/v1/workflow/chat', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: s.turns[i], session_id: session, confirmation_id: confirmation})});
      status = r.status; data = await r.json();
    } catch (e) { err = String(e); }
    const ms = Date.now() - t0;
    const item = {scenario: s.id, turn: i, message: s.turns[i], http_status: status, ms};
    if (status === 200 && data) {
      session = (data.state && data.state.session_id) || session;
      confirmation = data.confirmation_id || null;
      // keep everything the scorer needs; trim the bulky evidence array
      const ev = data.evidence || [];
      data.evidence = ev.slice(0, 40);
      data.evidence_count = ev.length;
      if (data.state) data.state = {session_id: data.state.session_id, active_order: data.state.active_order, last_intent: data.state.last_intent, pending_action: data.state.pending_action ? {kind: data.state.pending_action.kind, order_id: data.state.pending_action.order_id} : null};
      item.response = data;
      out.push({id: s.id, turn: i + 1, ms, intent: data.intent, clar: data.needs_clarification, conf: data.confirmation_required, sel: data.selected_order_id, tools: (data.tool_calls || []).map(t => t.name + (t.executed ? '!' : '')), answer: (data.answer || '').slice(0, 160)});
    } else { item.error = data || err; out.push({id: s.id, turn: i + 1, http_status: status, error: JSON.stringify(data || err).slice(0, 200)}); }
    window.__tp_eval[s.id].push(item);
  }
}
out
"""

DUMP = r"""
const all = [].concat(...Object.values(window.__tp_eval || {}));
const text = JSON.stringify({meta: {run_at: new Date().toISOString(), target: window.THREADPILOT_API_BASE, model: (all.find(x => x.response && x.response.model) || {response: {}}).response.model, first_pass: true, runner: 'browser'}, results: all});
const CH = %CHUNK%; const idx = %INDEX%;
({total_chars: text.length, chunks: Math.ceil(text.length / CH), index: idx, chunk: text.slice(idx * CH, (idx + 1) * CH)})
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--eval', default='eval_set.json', type=Path)
    ap.add_argument('--outdir', default='browser_batches', type=Path)
    ap.add_argument('--per-batch', type=int, default=4)
    args = ap.parse_args()
    ev = json.loads(args.eval.read_text(encoding='utf-8'))
    args.outdir.mkdir(exist_ok=True)
    compact = [{'id': s['id'], 'turns': [t['message'] for t in s['turns']]} for s in ev['scenarios']]
    batches = [compact[i:i + args.per_batch] for i in range(0, len(compact), args.per_batch)]
    for n, b in enumerate(batches, 1):
        (args.outdir / f'batch{n:02d}.js').write_text(RUNNER.replace('%SCENARIOS%', json.dumps(b, ensure_ascii=False)), encoding='utf-8')
    (args.outdir / 'dump.js').write_text(DUMP, encoding='utf-8')
    print(f'{len(batches)} batches written to {args.outdir}: ' + ', '.join(','.join(s['id'] for s in b) for b in batches))


if __name__ == '__main__':
    main()
