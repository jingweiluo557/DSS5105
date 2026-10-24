"""Run eval_set.json through WorkflowEngine.converse() with annotated classifications (no language model).

This isolates the deterministic server (routing, slot merging, clarifications, confirmation gate, tools) from the
planner. It runs offline against the CSVs in seconds and is the regression test for the Sprint 2 fixes.

    cd threadpilot/evaluation && python run_annotated_eval.py [--backend ../backend] [--data ../data] [--out transcript_annotated.json]
    python score.py --eval eval_set.json --transcript transcript_annotated.json --out results_annotated.json --report REPORT_annotated.md

The transcript has the same shape as the live one, so score.py and verify_tool_results.py apply unchanged.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from annotations import ANNOTATIONS  # noqa: E402


class ScriptedPlanner:
    """Stands in for ConversationAgent: returns the annotated classification, narrates by joining the server answers."""
    client = None
    degraded = True
    api_style = 'responses'

    def __init__(self, script):
        from app.conversation import Plan, Task
        from app.schemas import Classification, Intent, Slots
        self.script, self.Plan, self.Task, self.Classification, self.Intent, self.Slots = script, Plan, Task, Classification, Intent, Slots
        self.turn = 0

    async def plan(self, message, state, now):
        spec = dict(self.script[self.turn] or {})
        self.turn += 1
        intent = self.Intent(spec.pop('intent'))
        confidence = spec.pop('confidence', 0.95)
        return self.Plan(tasks=[self.Task(message=message, classification=self.Classification(intent=intent, confidence=confidence, slots=self.Slots(**spec)))])

    async def narrate(self, message, state, responses, emit=None):
        return '\n\n'.join(r.answer for r in responses)

    async def compose_chase(self, request, revision, facts, order_ids, previous, fallback, emit=None, **kwargs):
        return fallback


class RecordingSender:
    def __init__(self):
        self.sent = []

    async def send(self, payload, idempotency_key):
        self.sent.append({'payload': payload, 'id': idempotency_key})
        return 'test-receipt'


async def run(args):
    sys.path.insert(0, str(args.backend.resolve()))
    from app.schemas import ChatRequest, DialogState
    from app.workflow_engine import WorkflowEngine
    from app.workflow_store import WorkflowStore
    from app.workflow_tools import DataTools
    ev = json.loads(args.eval.read_text(encoding='utf-8'))
    now = datetime.fromisoformat(ev['business_now'])
    results, sender = [], RecordingSender()
    with tempfile.TemporaryDirectory() as tmp:
        for s in ev['scenarios']:
            if args.only and s['id'] not in args.only.split(','):
                continue
            script = ANNOTATIONS.get(s['id'])
            if script is None:
                print(f"{s['id']}: no annotation, skipped")
                continue
            engine = WorkflowEngine(DataTools(args.data), WorkflowStore(Path(tmp) / f"{s['id']}.sqlite3"), lambda: now, sender)
            planner = ScriptedPlanner(script)
            state = DialogState()
            engine.store.save(state)
            confirmation = None
            for i, t in enumerate(s['turns']):
                try:
                    resp = await engine.chat(ChatRequest(message=t['message'], session_id=state.session_id, confirmation_id=confirmation), planner)
                    state = resp.state
                    confirmation = resp.confirmation_id
                    data = resp.model_dump(mode='json')
                    data['model'] = 'annotated-planner'
                    results.append({'scenario': s['id'], 'turn': i, 'message': t['message'], 'http_status': 200, 'ms': 0, 'response': data})
                    print(f"{s['id']}.{i + 1} {resp.intent:<22} clar={int(resp.needs_clarification)} conf={int(resp.confirmation_required)} {resp.answer[:110]!r}")
                except Exception as exc:  # the live API would map this to an HTTP error
                    results.append({'scenario': s['id'], 'turn': i, 'message': t['message'], 'http_status': 500, 'ms': 0, 'error': {'error': {'code': type(exc).__name__, 'message': str(exc)}}})
                    print(f"{s['id']}.{i + 1} ERROR {type(exc).__name__}: {exc}")
                    if script[i] is not None and i + 1 < len(s['turns']):
                        planner.turn += 0  # keep the script aligned: the failed turn consumed its annotation already
    args.out.write_text(json.dumps({'meta': {'run_at': datetime.now(timezone.utc).isoformat(), 'target': 'in-process WorkflowEngine (CSV)', 'model': 'annotated-planner', 'first_pass': False,
                                             'runner': 'run_annotated_eval.py', 'sent_externally': sender.sent}, 'results': results}, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'wrote {args.out} ({len(results)} turns); external sends: {len(sender.sent)}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backend', type=Path, default=HERE.parent / 'backend')
    ap.add_argument('--data', type=Path, default=HERE.parent / 'data')
    ap.add_argument('--eval', type=Path, default=HERE / 'eval_set.json')
    ap.add_argument('--out', type=Path, default=HERE / 'transcript_annotated.json')
    ap.add_argument('--only', default='')
    asyncio.run(run(ap.parse_args()))


if __name__ == '__main__':
    main()
