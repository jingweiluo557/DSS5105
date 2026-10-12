"""Discovery and risk for the live backend, from the same engine as the morning briefing.

The dashboard chat and the briefing page use `simulation/briefing.py`: eight kinds of finding, each with a score and the
rows behind it, and a risk level per order from a day-by-day projection of the queue (`simulation/prediction.py`). Before
this module the live backend had neither: it could only read the saved 07:00 summary, and its "risk" was a 7-day
threshold flag that could disagree with the dashboard. Now the live tools call the same engine on the rows they already
read (CSV in tests, MySQL in production), so there is one definition of a finding and one definition of risk.

Nothing here is computed by the language model. The engine is standard-library Python with no randomness.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

from .schemas import Evidence

try:                                   # deployed: /srv/threadpilot or /var/user is on the path (Dockerfile, scf_bootstrap)
    from simulation import briefing as engine
except ModuleNotFoundError:            # running from backend/ in a checkout: the engine sits next to it
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from simulation import briefing as engine

TOP_N = engine.TOP_N
RISK_RULE = engine.DEFINITIONS['risk']
RANKING_RULE = engine.DEFINITIONS['ranking']


def _engine_rows(evidence: list[Evidence], number: str) -> list[dict[str, Any]]:
    rows = []
    for e in evidence:
        row = dict(e.record)
        row[number] = int(float(row[number]))
        row['_file'], row['_row'] = e.source, e.row
        rows.append(row)
    return rows


def run(tools: Any, business_date: date) -> tuple[dict[str, Any], dict[tuple[str, int], Evidence]]:
    """The full briefing for `business_date`, plus a lookup from (source, row) back to the source record."""
    orders, log = tools.rows('orders.csv'), tools.rows('production_log.csv')
    result = engine.build_rows(_engine_rows(orders, 'pieces'), _engine_rows(log, 'pieces_completed'), business_date)
    index = {(e.source, e.row): e for e in orders + log}
    result['data_through'] = max((e.record['date'] for e in log if e.record['date'] < business_date.isoformat()), default=None)
    return result, index


def evidence_of(finding: dict[str, Any], index: dict[tuple[str, int], Evidence]) -> list[Evidence]:
    """The source records behind one finding, as the backend's Evidence objects (so every number links to its row)."""
    return [index[(ref['file'], ref['row'])] for ref in finding.get('evidence', []) if (ref['file'], ref['row']) in index]


def findings(tools: Any, business_date: date) -> dict[str, Any]:
    """Tool list_findings: what is unusual this morning, ranked, top five. Same eight kinds and scores as the briefing page."""
    result, index = run(tools, business_date)
    top = result['findings']
    return {
        'business_date': result['business_date'], 'covers': result['covers'], 'data_through': result['data_through'],
        'findings': [{k: f[k] for k in ('key', 'type', 'title', 'detail', 'score', 'score_reason', 'severity', 'next_step', 'order_ids')}
                     for f in top],
        'more_findings': result['more_findings'],
        'status_counts': result['status_counts'],
        'ranking': RANKING_RULE,
        'limits': 'Ranked by a stated score, not by the model. A finding is a pattern in the recorded data, not a confirmed cause.',
        '_evidence': [e for f in top for e in evidence_of(f, index)],
    }


def risk_levels(tools: Any, business_date: date) -> dict[str, dict[str, Any]]:
    """Risk level for every in-progress order, by order ID: the same projection the dashboard shows."""
    result, _ = run(tools, business_date)
    return {o['order_id']: o['risk'] for o in result['orders']}


def saved_findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The top findings for the 07:00 briefing that the cloud timer saves, from the dashboard's snapshot of the database.

    Each row keeps its database record ID, so a finding can still be traced to /api/evidence/<table>/<id>."""
    def rows(name: str, number: str) -> list[dict[str, Any]]:
        out = []
        for r in data[name]:
            row = {k: v for k, v in r.items() if not k.startswith('_')}
            row[number] = int(float(row[number]))
            row['_file'], row['_row'] = name, r['_record_id']
            out.append(row)
        return out
    result = engine.build_rows(rows('orders', 'pieces'), rows('production_log', 'pieces_completed'), date.fromisoformat(data['today']))
    return [{k: f[k] for k in ('key', 'title', 'detail', 'score', 'severity', 'next_step', 'order_ids')} for f in result['findings']]
