"""Dashboard calculations use business dates; scheduling uses the UTC+8 wall clock."""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
import json
import math

import sqlalchemy as sa
from ..dashboard_store import tasks, briefings, metrics
from ..forecast_store import load_forecasts
from ..sql_workflow_store import SQLWorkflowStore

LOCAL = timezone(timedelta(hours=8))
STAGES = ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING']

@lru_cache(maxsize=1)
def forecast_asset():
    return json.loads((Path(__file__).resolve().parents[1] / 'assets/order_forecasts.json').read_text(encoding='utf-8'))

def canonical(rows, fields):
    numeric = {'pieces', 'days_late', 'pieces_completed', 'capacity_pieces_per_day', 'pickup_lead_days',
               'defect_rate', 'cost_per_piece', 'max_batch_pieces', 'current_queue_days'}
    def value(row, key):
        v = row.get(key, '')
        if v is None or v == '':
            return ''
        return str(float(v)) if key in numeric else str(v)
    return sorted(tuple(value(r, k) for k in fields) for r in rows)

def forecast_matches(data, asset=None):
    asset = forecast_asset() if asset is None else asset
    if data['today'] != asset['business_date']:
        return False
    for name, rows in asset['sources'].items():
        fields = sorted(rows[0])
        if canonical(data[name], fields) != canonical(rows, fields):
            return False
    return True

def analyze(data, asset=None):
    asset = forecast_asset() if asset is None else asset
    today = date.fromisoformat(data['today'])
    active = [r for r in data['orders'] if r['status'] == 'IN_PROGRESS']
    customers = Counter(r['customer'] for r in active)
    valid_forecast = forecast_matches(data, asset)
    forecasts = asset['forecasts'] if valid_forecast else {}
    evaluated = []
    for r in active:
        due = (date.fromisoformat(r['due_date']) - today).days
        idle = max(0, (today - date.fromisoformat(r['last_activity_date'])).days)
        score = (min(35, idle * 5) + (35 if due < 0 else 28 if due <= 3 else 20 if due <= 7 else 10 if due <= 14 else 0)
                 + (4 - STAGES.index(r['current_stage'])) * 5 + math.floor(customers[r['customer']] / len(active) * 10 + .5))
        prediction = forecasts.get(r['order_id'], {}).get('prediction')
        high = prediction['delay_probability'] >= .6 if prediction else score >= 60
        reasons = []
        if due < 0: reasons.append('Overdue')
        elif due <= 7: reasons.append('Due within 7 days')
        if high or score >= 60: reasons.append('High risk')
        if idle >= 5: reasons.append('No activity for 5+ days')
        evaluated.append({**r, 'score': score, 'idle': idle, 'due_days': due, 'high': high,
                          'prediction': prediction, 'reasons': reasons})
    counts = {'in_progress': len(active), 'overdue': sum(r['due_days'] < 0 for r in evaluated),
              'due_today': sum(r['due_days'] == 0 for r in evaluated), 'idle': sum(r['idle'] >= 5 for r in evaluated),
              'priority': sum(r['score'] >= 60 for r in evaluated)}
    late = counts['overdue']
    risk = sum(r['due_days'] >= 0 and r['high'] for r in evaluated)
    health = {'late': late, 'at_risk': risk, 'on_track': len(active) - late - risk,
              'basis': 'Imported delay model ≥60%' if valid_forecast else 'Priority score ≥60 (forecast unavailable)'}
    def delivery(start, end):
        rows = [r for r in data['orders'] if r['status'] == 'COMPLETE' and r.get('completed_date')
                and start <= date.fromisoformat(r['completed_date']) < end]
        on_time = sum(float(r['days_late']) <= 0 for r in rows)
        return {'total': len(rows), 'on_time': on_time, 'rate': round(on_time / len(rows) * 100, 1) if rows else None}
    health['delivery'] = delivery(today - timedelta(days=30), today)
    health['prior_delivery'] = delivery(today - timedelta(days=60), today - timedelta(days=30))
    production = []
    for stage in STAGES:
        rows = sorted([r for r in data['production_log'] if r['stage'] == stage and r['date'] < data['today']
                       and date.fromisoformat(r['date']).weekday() != 6], key=lambda r: r['date'])
        if not rows: continue
        latest, previous = rows[-1], rows[-21:-1]
        baseline = sum(float(r['pieces_completed']) for r in previous) / len(previous) if previous else None
        production.append({'stage': stage, 'date': latest['date'], 'pieces': float(latest['pieces_completed']),
                           'baseline': baseline, 'change': (float(latest['pieces_completed']) / baseline - 1) * 100 if baseline else None})
    weakest = min((r for r in production if r['change'] is not None), key=lambda r: r['change'], default=None)
    advice = []
    if late:
        selected = sorted([r for r in evaluated if r['due_days'] < 0], key=lambda r: r['due_days'])[:3]
        advice.append({'title': 'Confirm revised delivery dates', 'text': f'{late} orders are already overdue. Confirm remaining work and a revised date before making new promises.', 'orders': [r['order_id'] for r in selected]})
    if valid_forecast:
        selected = sorted([r for r in evaluated if r['due_days'] >= 0 and r['high']], key=lambda r: -r['prediction']['delay_probability'])[:3]
        if selected:
            advice.append({'title': 'Review predicted delivery risk', 'text': 'These orders are not overdue yet but have elevated model risk. Verify progress and capacity with production.',
                           'orders': [r['order_id'] for r in selected], 'probabilities': {r['order_id']: r['prediction']['delay_probability'] for r in selected}})
    if weakest and weakest['change'] < 0:
        advice.append({'title': f"Check {weakest['stage'].title()} capacity", 'text': f"Latest output is {abs(weakest['change']):.1f}% below the previous {min(20, len(data['production_log']))} working-day baseline. Check staffing, WIP and upstream supply before reallocating work.", 'orders': []})
    # Compare queue + pickup + full-order production, never allocate multiple orders to the same capacity.
    candidates = sorted([r for r in evaluated if r['reasons']], key=lambda r: (r['due_days'], -r['score']))
    if candidates:
        order = candidates[0]
        options = []
        for w in data['workshops']:
            cap = float(w['capacity_pieces_per_day']) * (1 - float(w['defect_rate']))
            limit = float(w['max_batch_pieces']) if w.get('max_batch_pieces') else None
            if w['status'] != 'ACTIVE' or order['category'] not in w['makes'].split('+') or cap <= 0 or (limit and float(order['pieces']) > limit): continue
            days = float(w['current_queue_days']) + float(w['pickup_lead_days']) + float(order['pieces']) / cap
            options.append({'id': w['workshop_id'], 'name': w['name'], 'days': round(days, 1), 'cost': float(order['pieces']) * float(w['cost_per_piece'])})
        options.sort(key=lambda w: (w['days'], w['cost']))
        if options:
            best = options[0]
            advice.append({'title': 'Compare an outsourcing option', 'text': f"For {order['order_id']}, {best['name']} has the shortest eligible isolated estimate ({best['days']} calendar days, including queue and pickup). Confirm remaining quantity and reserved capacity; this is not a delivery promise.", 'orders': [order['order_id']], 'options': options[:3]})
    concise = []
    urgent = sorted(evaluated, key=lambda r: (r['due_days'], -r['score']))[:3]
    if late or risk:
        concise.append({'title': 'Review urgent deliveries',
            'text': f'{late} overdue; {risk} additional orders at risk. Confirm progress and revised delivery dates.',
            'orders': [r['order_id'] for r in urgent], 'source': 'priority'})
    if weakest and weakest['change'] < 0:
        concise.append({'title': f"Restore {weakest['stage'].title()} output",
            'text': f"Output is {abs(weakest['change']):.1f}% below baseline. Check staffing and upstream supply before reallocating work.",
            'orders': [], 'source': 'production'})
    external = next((a for a in advice if a.get('options')), None)
    if external:
        option = external['options'][0]
        concise.append({'title': 'Check an outsourcing option',
            'text': f"{external['orders'][0]}: {option['name']}, approximately {option['days']} calendar days. Confirm remaining work and available capacity.",
            'orders': external['orders'], 'options': external['options'], 'source': 'capacity'})
    advice = concise[:3]
    return {'counts': counts, 'health': health, 'orders': evaluated, 'production': production, 'advice': advice,
            'forecast': {'available': valid_forecast, 'business_date': asset['business_date'],
                         'type': 'Order delay risk, not sales demand', 'training_samples': 86,
                         'reason': None if valid_forecast else 'Forecast source data or business date has changed. Refresh the forecast to use model risk.'},
            'sales_forecast_available': False}

class DashboardService:
    def __init__(self, database):
        self.database = database
        self.store = SQLWorkflowStore(database.engine)

    def sync(self, data, result, now):
        stamp = now.isoformat()
        with self.store.turn_lock('dashboard-sync'), self.database.engine.begin() as db:
            for order in result['orders']:
                key = 'auto:' + order['order_id']
                old = db.execute(sa.select(tasks).where(tasks.c.id == key)).mappings().first()
                if not order['reasons'] and old is None: continue
                values = {'id': key, 'order_id': order['order_id'], 'title': f"{order['order_id']} · {order['customer']}",
                          'origin': 'auto', 'done': False, 'business_date': data['today'], 'reasons': json.dumps(order['reasons']),
                          'version': 1, 'created_at': stamp, 'updated_at': stamp}
                if old is None:
                    self.store.upsert(db, tasks, values)
                else:
                    changes = {'title': values['title'], 'reasons': values['reasons']}
                    if old['done'] and old['business_date'] < data['today'] and order['reasons']:
                        changes.update(done=False, business_date=data['today'])
                    if any(old[k] != v for k, v in changes.items()):
                        db.execute(tasks.update().where(tasks.c.id == key, tasks.c.version == old['version']).values(**changes, version=old['version']+1, updated_at=stamp))
            active_ids = [r['order_id'] for r in result['orders']]
            db.execute(tasks.update().where(tasks.c.origin == 'auto', tasks.c.order_id.not_in(active_ids), tasks.c.reasons != '[]')
                       .values(reasons='[]', version=tasks.c.version+1, updated_at=stamp))
            self.store.upsert(db, metrics, {'business_date': data['today'], 'payload': json.dumps(result['counts'])}, ['payload'])

    def list_tasks(self):
        with self.database.engine.connect() as db:
            rows = db.execute(sa.select(tasks).order_by(tasks.c.done, tasks.c.created_at, tasks.c.id)).mappings().all()
        return [{**r, 'reasons': json.loads(r['reasons'])} for r in rows]

    def create_task(self, title, day, now, task_id):
        values = {'id': 'manual:' + str(task_id), 'order_id': None, 'title': title.strip(), 'origin': 'manual', 'done': False,
                  'business_date': day, 'reasons': '[]', 'version': 1, 'created_at': now.isoformat(), 'updated_at': now.isoformat()}
        if not values['title']: raise ValueError('Task title cannot be blank.')
        with self.database.engine.begin() as db:
            self.store.upsert(db, tasks, values)
        return values['id']

    def complete_task(self, task_id, done, version, now):
        with self.database.engine.begin() as db:
            changed = db.execute(tasks.update().where(tasks.c.id == task_id, tasks.c.version == version)
                                 .values(done=done, version=version+1, updated_at=now.isoformat()))
            return changed.rowcount == 1

    def get(self, data):
        result = analyze(data, load_forecasts(self.database))
        self.sync(data, result, datetime.now(LOCAL))
        with self.database.engine.connect() as db:
            history = db.execute(sa.select(metrics).where(metrics.c.business_date <= data['today']).order_by(metrics.c.business_date.desc()).limit(14)).mappings().all()
            reports = db.execute(sa.select(briefings).order_by(briefings.c.day.desc()).limit(30)).mappings().all()
        return {**result, 'business_date': data['today'], 'tasks': self.list_tasks(),
                'history': [{'date': r['business_date'], **json.loads(r['payload'])} for r in reversed(history)],
                'briefing_preview': {'business_date': data['today'], **self.compose_briefing(data, result, datetime.now(LOCAL))},
                'briefings': [{'day': r['day'], 'business_date': r['business_date'], 'generated_at': r['generated_at'], **json.loads(r['payload'])} for r in reports]}

    def generate_due(self, data, now):
        now = now.astimezone(LOCAL)
        if now.hour < 7: return {'status': 'not_due'}
        day = now.date().isoformat()
        with self.store.turn_lock('dashboard-briefing'):
            with self.database.engine.connect() as db:
                if db.execute(sa.select(briefings.c.day).where(briefings.c.day == day)).first():
                    return {'status': 'already_saved', 'day': day}
            result = analyze(data, load_forecasts(self.database))
            # Separate lock from report lock: tasks and observed metrics share the same business snapshot.
            self.sync(data, result, now)
            payload = self.compose_briefing(data, result, now)
            with self.database.engine.begin() as db:
                self.store.upsert(db, briefings, {'day': day, 'business_date': data['today'], 'generated_at': now.isoformat(), 'payload': json.dumps(payload)})
        return {'status': 'completed', 'day': day}

    def compose_briefing(self, data, result, now):
        yesterday = (date.fromisoformat(data['today']) - timedelta(days=1)).isoformat()
        output = [r for r in data['production_log'] if r['date'] == yesterday]
        worst = min((r for r in result['production'] if r['change'] is not None), key=lambda r:r['change'], default=None)
        queued = sorted([r for r in result['orders'] if r['reasons']], key=lambda r:(r['due_days'], -r['score']))
        top = queued[0] if queued else None
        completed = [r for r in self.list_tasks() if r['done'] and r['updated_at'][:10] == now.date().isoformat()]
        payload = {'yesterday': f"{sum(int(float(r['pieces_completed'])) for r in output):,} stage completions across {len(set(r['stage'] for r in output))} stages on {yesterday}." if output else f'No production record for {yesterday}.',
                   'top_issue': f"{top['order_id']} · {top['customer']}: {', '.join(top['reasons']).lower()}." if top else 'No orders currently flagged.',
                   'decide': f"{result['counts']['overdue']} overdue; {sum(0 <= r['due_days'] <= 7 for r in result['orders'])} due within 7 days.",
                   'production_note': f"{worst['stage'].title()} {abs(worst['change']):.1f}% {'below' if worst['change'] < 0 else 'above'} baseline." if worst else None,
                   'cleared': [r['title'] for r in completed], 'health': result['health'], 'advice': result['advice']}
        return payload
