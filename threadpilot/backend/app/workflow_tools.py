"""场景 1.1–2.2：刷新 CSV、逐行证据与可解释计算。"""
import csv
import math
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from .schemas import Evidence, Slots

STAGES = ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING']


def resolve_datetime(value: str, now: datetime, previous: datetime | None = None) -> datetime | None:
    """场景 3.1/3.3：相对时间归一化；仅有 morning 等模糊时间时返回空。"""
    raw = value.strip()
    try:
        result = datetime.fromisoformat(raw)
        if 't' in raw.lower() or ' ' in raw:
            return result.astimezone(now.tzinfo) if result.tzinfo else result.replace(tzinfo=now.tzinfo)
    except ValueError:
        pass
    value = raw.lower().replace('.', '')
    value = value.replace('两分钟','2分钟').replace('二分钟','2分钟').replace('一分钟','1分钟').replace('two minutes','2 minutes').replace('one minute','1 minute')
    relative = re.fullmatch(r'(?:in\s+)?(\d+)\s*(minutes?|hours?|seconds?|分钟|小时|秒)(?:\s*(?:later|后))?',value)
    if relative:
        seconds=int(relative[1])*(3600 if relative[2] in ('hour','hours','小时') else 60 if relative[2] in ('minute','minutes','分钟') else 1)
        return now+timedelta(seconds=seconds) if 0 < seconds <= 604800 else None
    try:
        result = datetime.fromisoformat(value)
        if 't' not in value and ' ' not in value:
            return None
        return result if result.tzinfo else result.replace(tzinfo=now.tzinfo)
    except ValueError:
        pass
    day = previous.date() if previous else now.date()
    if 'tomorrow' in value or '明天' in value:
        day = now.date() + timedelta(days=1)
    elif 'today' in value or '今天' in value:
        day = now.date()
    for index, name in enumerate(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
        if name in value:
            day = now.date() + timedelta(days=(index - now.weekday()) % 7 or 7)
    if 'noon' in value or '中午' in value:
        return datetime.combine(day, time(12), tzinfo=now.tzinfo)
    match = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', value)
    if not match:
        return None
    hour, minute = int(match[1]), int(match[2] or 0)
    if not 1 <= hour <= 12 or minute > 59:
        return None
    return datetime.combine(day, time(hour % 12 + (12 if match[3] == 'pm' else 0), minute), tzinfo=now.tzinfo)


WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


def resolve_date(value: str, now: datetime) -> date:
    """场景 1.5/2.1/2.2：以显式业务时钟解析日期，不偷偷滚动过期日期。

    Accepts ISO dates, 'today/yesterday/tomorrow', 'in N (working) days', 'the 25th' (this month, by the business
    clock) and weekday names: 'Saturday', 'this Saturday', 'next Monday' (the next such day after today; 'next'
    skips one more week when the day is within the coming week)."""
    lowered = value.strip().lower().rstrip('.')
    weekday = re.fullmatch(r'(?:(this|next|coming|on)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)', lowered)
    if weekday:
        name = next(w for w in WEEKDAYS if w.startswith(weekday[2][:3]))
        ahead = (WEEKDAYS.index(name) - now.weekday()) % 7 or 7
        if weekday[1] == 'next' and ahead < 7:
            ahead += 7
        return now.date() + timedelta(days=ahead)
    relative = re.fullmatch(r'(?:in\s+)?(\d+)\s*(working|business|calendar)?\s*days?', lowered)
    chinese = re.fullmatch(r'(\d+)个?(工作日|天)(?:后|内)?', lowered)
    if relative or chinese:
        count = int((relative or chinese)[1])
        if count > 730:
            raise ValueError('Date window too large')
        working = relative and relative[2] in ('working', 'business') or chinese and chinese[2] == '工作日'
        day = now.date()
        while count:
            day += timedelta(days=1)
            if not working or day.weekday() != 6:
                count -= 1
        return day
    if lowered in ('today', '今天'):
        return now.date()
    if lowered in ('yesterday', '昨天'):
        return now.date() - timedelta(days=1)
    if lowered in ('tomorrow', '明天'):
        return now.date() + timedelta(days=1)
    match = re.fullmatch(r'(?:the )?(\d{1,2})(?:st|nd|rd|th)', lowered)
    return now.date().replace(day=int(match[1])) if match else date.fromisoformat(value)


class DataTools:
    def __init__(self, directory: Path) -> None:
        """场景 1.1–2.2：只读取正式数据目录。"""
        self.directory = directory

    def rows(self, source: str) -> list[Evidence]:
        """场景 1.2/2.2：每次重新读取原始记录，保留 CSV 记录行号。"""
        if source not in ('orders.csv', 'production_log.csv', 'workshops.csv'):
            raise ValueError('Unsupported source')
        with (self.directory / source).open(encoding='utf-8-sig', newline='') as stream:
            return [Evidence(source=source, row=index, url=f'/api/v1/evidence/{source}/{index}', record=row)
                    for index, row in enumerate(csv.DictReader(stream), 2)]

    def search_orders(self, slots: Slots) -> list[Evidence]:
        """场景 1.1：按用户明确给出的约束求交集，绝不选择第一条。"""
        matches = []
        for evidence in self.rows('orders.csv'):
            row = evidence.record
            if slots.order_ids:
                if row['order_id'] not in slots.order_ids:
                    continue
            elif row['status'] != 'IN_PROGRESS':
                continue
            if slots.customer and slots.customer.casefold() != row['customer'].casefold():
                continue
            if slots.product and slots.product.casefold().rstrip('s') not in row['product'].casefold():
                continue
            if slots.quantity is not None and slots.quantity != int(row['pieces']):
                continue
            if slots.due_date and slots.due_date != row['due_date']:
                continue
            matches.append(evidence)
        return matches

    def refresh_order(self, order_id: str) -> Evidence:
        """场景 1.2/1.3/3.1–3.3：从磁盘刷新选定订单的全部字段。"""
        matches = [e for e in self.rows('orders.csv') if e.record['order_id'] == order_id]
        if len(matches) != 1:
            raise ValueError('Unknown or duplicate order ID')
        return matches[0]

    def queue_snapshot(self, now):
        data = {'today': now.date().isoformat(), 'schedule': {'version': 0, 'priority': []}}
        evidence = []
        for name in ('orders', 'production_log', 'workshops'):
            rows = self.rows(name + '.csv')
            evidence.extend(rows)
            data[name] = [e.record for e in rows]
        return data, evidence

    def assess_risk(self, order: Evidence, now: datetime) -> dict[str, Any]:
        from .services.queue_engine import QueueAnalysis
        data, _ = self.queue_snapshot(now)
        current = next((o for o in data['orders'] if o['order_id'] == order.record['order_id']), None)
        if current is None:
            raise ValueError('Order no longer exists. Refresh the conversation.')
        engine = QueueAnalysis(data)
        risk = engine.risk(current)
        return {'order_id': current['order_id'], 'risk_level': risk['level'], **risk,
                'risk_flag': risk['level'] in ('high', 'medium', 'overdue'),
                'overdue': risk['level'] == 'overdue',
                'completed_late': current['status'] == 'COMPLETE' and int(current.get('days_late') or 0) > 0,
                'idle_days': max(0, (now.date() - date.fromisoformat(current['last_activity_date'])).days),
                'days_to_due': (date.fromisoformat(current['due_date']) - now.date()).days,
                'activity_observation': f"Last recorded activity was {max(0, (now.date() - date.fromisoformat(current['last_activity_date'])).days)} days before the business date; calendar gap, not proof of a stoppage.",
                'reasons': [risk['reason']], 'assumptions': engine.context()['assumptions'],
                'limits': 'A projected risk is not confirmed late delivery. Recorded overdue status is a separate fact. No per-order event history or recorded blockers exists in this dataset.'}

    def expedite(self, order_id, now):
        from .services.queue_engine import QueueAnalysis
        data, evidence = self.queue_snapshot(now)
        return QueueAnalysis(data).expedite(order_id), evidence

    def prioritize(self, slots: Slots, now: datetime) -> tuple[dict[str, Any], list[Evidence]]:
        """场景 1.6：到期窗口包含逾期未完成订单，按截止日、旧更新、ID 排序。"""
        end = now.date() + timedelta(days=slots.window_days or 0)
        rows = [e for e in self.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS'
                and date.fromisoformat(e.record['due_date']) <= end
                and (not slots.customer or e.record['customer'].casefold() == slots.customer.casefold())]
        rows.sort(key=lambda e: (e.record['due_date'], e.record['last_activity_date'], e.record['order_id']))
        return {'business_now': now.isoformat(), 'window_start': now.date().isoformat(), 'window_end': end.isoformat(), 'rule': 'Earlier due date first; ties: older last activity, then order ID. Includes overdue active orders. No opaque score.',
                'orders': [self.assess_risk(e, now) for e in rows]}, rows

    def normality(self, slots: Slots, now: datetime) -> tuple[dict[str, Any], list[Evidence]]:
        """场景 2.1：使用前八个同 weekday 的原始行比较，单次低值不确诊。"""
        target = resolve_date(slots.target_date or 'today', now)
        rows = [e for e in self.rows('production_log.csv') if e.record['stage'] == slots.stage]
        baseline = sorted([e for e in rows if date.fromisoformat(e.record['date']) < target
                           and date.fromisoformat(e.record['date']).weekday() == target.weekday()],
                          key=lambda e: e.record['date'])[-8:]
        observed = [e for e in rows if e.record['date'] == target.isoformat()]
        output = slots.observed_output
        provenance = 'user-provided observation; not verified by source'
        if observed:
            output = int(observed[0].record['pieces_completed'])
            provenance = 'production_log.csv'
        if len(baseline) < 3 or target.weekday() == 6 or output is None:
            return {'status': 'insufficient_baseline_or_observation', 'date': target.isoformat(),
                    'sample_count': len(baseline), 'note': 'Need at least 3 prior same-weekday working records and an observation.'}, baseline + observed
        values = [int(e.record['pieces_completed']) for e in baseline]
        return {'stage': slots.stage, 'date': target.isoformat(), 'output': output,
                'baseline_records': [{'date': e.record['date'], 'pieces_completed': int(e.record['pieces_completed']), 'source': e.source, 'row': e.row} for e in baseline],
                'observation_source': provenance, 'user_observation': slots.observed_output,
                'sample_count': len(values), 'baseline': 'previous eight same weekdays, excluding target and future dates',
                'minimum': min(values), 'maximum': max(values), 'mean': round(mean(values), 2),
                'status': 'below' if output < min(values) else 'above' if output > max(values) else 'within',
                'limits': 'Descriptive historical range, not a statistical control limit. One low observation alone is not proof of a sustained problem.'}, baseline + observed

    def deviation(self, slots: Slots, now: datetime) -> tuple[dict[str, Any], list[Evidence]]:
        """场景 2.2：展示当日上下游和同 weekday 对照，不把共现当因果。"""
        target = resolve_date(slots.target_date or 'yesterday', now)
        rows = [e for e in self.rows('production_log.csv') if e.record['date'] == target.isoformat()]
        comparison, baseline = self.normality(slots.model_copy(update={'target_date': target.isoformat()}), now)
        return {'date': target.isoformat(), 'comparison': comparison,
                'facts': [e.record for e in rows],
                'interpretation': 'These are co-occurring facts, not proof of causation. The lower-output premise must be checked against the comparison.',
                'missing': 'No blocker, downtime, staffing, or per-order event fields are available.',
                'next_check': 'Verify upstream throughput, staffing and downtime with the operator; check whether the pattern repeats.'}, rows + baseline

    def production_output(self, slots: Slots, now: datetime) -> tuple[dict[str, Any], list[Evidence]]:
        """Retrieval: recorded stage output on one date (all stages when no stage is given). No comparison, no judgement."""
        target = resolve_date(slots.target_date or 'yesterday', now)
        rows = [e for e in self.rows('production_log.csv') if e.record['date'] == target.isoformat()
                and (not slots.stage or e.record['stage'] == slots.stage)]
        data = {'date': target.isoformat(), 'weekday': target.strftime('%A'), 'stage': slots.stage,
                'records': [{'stage': e.record['stage'], 'pieces_completed': int(e.record['pieces_completed'])} for e in rows],
                'source': 'production_log.csv' if rows else None}
        if not rows:
            data['status'] = 'no_record'
            data['note'] = ('Sunday: the factory is closed.' if target.weekday() == 6 else
                            f'No production record for {target.isoformat()}; the log covers the dates present in production_log.csv only.')
        else:
            data['status'] = 'ok'
            data['note'] = 'Recorded stage output, not a judgement; ask whether it is normal to compare with the same weekday.'
        return data, rows

    def list_workshops(self, slots: Slots) -> tuple[dict[str, Any], list[Evidence]]:
        """Retrieval: outside workshops that can take a category / batch size, with suspended ones listed separately."""
        text = (slots.product or '').lower()
        category = 'ACCESSORIES' if any(word in text for word in ('scarf', 'scarves', 'beanie', 'accessor')) else 'TOPS' if text else None
        rows = self.rows('workshops.csv')
        quantity = slots.quantity
        eligible, excluded = [], []
        for e in rows:
            r = e.record
            reasons = []
            if r['status'] != 'ACTIVE':
                reasons.append(f"status {r['status']}: may not take new work")
            if category and category not in r['makes']:
                reasons.append(f"makes {r['makes']}, not {category}")
            if quantity and r['max_batch_pieces'] and quantity > int(r['max_batch_pieces']):
                reasons.append(f"batch cap {r['max_batch_pieces']} pieces")
            item = {'workshop_id': r['workshop_id'], 'name': r['name'], 'makes': r['makes'], 'status': r['status'],
                    'capacity_pieces_per_day': int(r['capacity_pieces_per_day']), 'pickup_lead_days': int(r['pickup_lead_days']),
                    'current_queue_days': float(r['current_queue_days']), 'defect_batch_probability': float(r['defect_rate']),
                    'cost_per_piece': float(r['cost_per_piece']), 'max_batch_pieces': int(r['max_batch_pieces']) if r['max_batch_pieces'] else None,
                    'notes': r['notes']}
            if quantity:
                item['estimated_batch_days'] = round(float(r['current_queue_days']) + float(r['pickup_lead_days']) + quantity / float(r['capacity_pieces_per_day']), 1)
            (excluded if reasons else eligible).append({**item, 'excluded_because': reasons} if reasons else item)
        eligible.sort(key=lambda w: (w.get('estimated_batch_days', w['current_queue_days']), w['workshop_id']))
        return {'category': category, 'quantity': quantity, 'eligible': eligible, 'excluded': excluded,
                'rule': 'ACTIVE status, category in makes, batch within max_batch_pieces; ordered by queue + pickup + quantity/capacity.',
                'limits': 'Profile cards only: no live availability, no price negotiation; defect rate is a batch probability, not a defective-piece share. Workshop choice stays with the dispatcher.'}, rows

    def rank_active_orders(self, slots: Slots, now: datetime) -> tuple[dict[str, Any], list[Evidence]]:
        """Judgement-free ranking of active orders by one explicit criterion (idle days or days to due)."""
        criterion = slots.criterion if slots.criterion in ('idle_days', 'due_date', 'last_activity_date') else 'idle_days'
        rows = [e for e in self.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS'
                and (not slots.customer or e.record['customer'].casefold() == slots.customer.casefold())]
        items = [{'order_id': e.record['order_id'], 'customer': e.record['customer'], 'product': e.record['product'], 'pieces': int(e.record['pieces']),
                  'current_stage': e.record['current_stage'], 'due_date': e.record['due_date'], 'last_activity_date': e.record['last_activity_date'],
                  'idle_days': (now.date() - date.fromisoformat(e.record['last_activity_date'])).days,
                  'days_to_due': (date.fromisoformat(e.record['due_date']) - now.date()).days} for e in rows]
        if criterion == 'idle_days':
            items.sort(key=lambda o: (-o['idle_days'], o['due_date'], o['order_id']))
            rule = 'Most calendar days since last recorded activity first; ties by due date, then order ID. A gap is not proof of a stoppage.'
        else:
            items.sort(key=lambda o: (o['due_date'], o['last_activity_date'], o['order_id']))
            rule = 'Earliest due date first (overdue first); ties by older last activity, then order ID.'
        limit = min(max(slots.window_days or 10, 1), 34)
        return {'criterion': criterion, 'rule': rule, 'business_date': now.date().isoformat(), 'count_active': len(items),
                'orders': items[:limit], 'truncated': len(items) > limit}, rows

    def new_order_queue(self, slots: Slots, now: datetime, due: date) -> dict[str, Any] | None:
        """Feasibility v2: insert the hypothetical order into the shared queue simulation (same calendar, capacity and
        priorities as assess_order_risk / assess_expedite) and read off when it would finish."""
        from .services.queue_engine import project, kth_working_day, working_days_inclusive
        from .services.queue_engine import QueueAnalysis
        data, _ = self.queue_snapshot(now)
        engine = QueueAnalysis(data)
        if not engine.available:
            return None
        new = {'order_id': 'NEW-ORDER', 'pieces': int(slots.quantity or 0), 'current_stage': 'KNITTING', 'due_date': due.isoformat(),
               'status': 'IN_PROGRESS', 'last_activity_date': now.date().isoformat()}
        active = engine.active + [new]
        best = project(active, engine.capacity, engine.today, priority=engine.priority)
        # Expected case: new orders keep arriving at the recent rate (last 45 days) with their usual promised lead time.
        start = (now.date() - timedelta(days=45)).isoformat()
        recent = [o for o in data['orders'] if start <= o['order_date'] < now.date().isoformat()]
        arrivals = None
        if len(recent) >= 5:
            leads = [(date.fromisoformat(o['due_date']) - date.fromisoformat(o['order_date'])).days for o in recent]
            workdays = working_days_inclusive(date.fromisoformat(start), now.date() - timedelta(days=1))
            arrivals = {'leads': leads, 'pieces_per_working_day': sum(int(o['pieces']) for o in recent) / max(workdays, 1)}
        expected = project(active, engine.capacity, engine.today, priority=engine.priority, arrivals=arrivals) if arrivals else best
        k_best, k_exp = best.get('NEW-ORDER'), expected.get('NEW-ORDER')
        width = working_days_inclusive(engine.today, due)
        out = {'method': 'shared queue simulation with the new order appended (earliest due date first, manager priorities kept)',
               'capacity_per_day': {k: round(v, 1) for k, v in engine.capacity.items()}, 'capacity_factor': engine.factor,
               'working_days_to_due_including_today': width,
               'best_case': {'finish_date': kth_working_day(engine.today, k_best).isoformat() if k_best else None, 'working_days': k_best,
                             'scenario': 'current orders only, no new arrivals'},
               'expected_case': {'finish_date': kth_working_day(engine.today, k_exp).isoformat() if k_exp else None, 'working_days': k_exp,
                                 'scenario': (f"new orders keep arriving at the last-45-day rate ({round(arrivals['pieces_per_working_day'])} pieces/working day)" if arrivals else 'no arrival history; same as best case')},
               'orders_ahead': len(engine.active), 'assumptions': engine.context()['assumptions']}
        if k_best is None:
            out['verdict'] = 'unlikely'
            out['reason'] = 'Does not finish within the 200-working-day horizon even with no new arrivals.'
        elif k_exp is not None and k_exp <= width:
            out['verdict'] = 'likely'
            out['reason'] = f"Finishes by {out['expected_case']['finish_date']} even if new orders keep arriving; due {due.isoformat()}."
        elif k_best <= width:
            out['verdict'] = 'tight'
            out['reason'] = f"Finishes by {out['best_case']['finish_date']} only if nothing new goes ahead of it; with usual arrivals {out['expected_case']['finish_date'] or 'beyond the horizon'}."
        else:
            out['verdict'] = 'unlikely'
            out['reason'] = f"Even with no new arrivals it finishes {out['best_case']['finish_date']}, {k_best - width} working days after the due date."
        return out

    def capacity(self, slots: Slots, now: datetime) -> tuple[dict[str, Any], list[Evidence]]:
        """场景 1.5：以历史产量和在制订单做保守串行估算及损失日情景。

        v2 (Sprint 2): the headline verdict comes from the shared queue simulation with the new order inserted; the
        AFT lead-time model adds the historical on-time probability for an order of this size; the serial-backlog sum
        is kept as a labelled worst case (it treats every active piece as ahead of the new order at every stage)."""
        due = resolve_date(slots.due_date or '', now)
        active = [e for e in self.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS']
        logs = [e for e in self.rows('production_log.csv') if date.fromisoformat(e.record['date']) < now.date()
                and date.fromisoformat(e.record['date']).weekday() != 6]
        selected: list[Evidence] = []
        stages = []
        for index, stage in enumerate(STAGES):
            sample = sorted([e for e in logs if e.record['stage'] == stage], key=lambda e: e.record['date'])[-20:]
            if not sample:
                raise ValueError('No capacity baseline')
            selected.extend(sample)
            rate = mean(int(e.record['pieces_completed']) for e in sample)
            if rate <= 0:
                raise ValueError('Nonpositive capacity baseline')
            load = sum(int(e.record['pieces']) for e in active if STAGES.index(e.record['current_stage']) <= index)
            days = math.ceil((load + (slots.quantity or 0)) / rate)
            stages.append({'stage': stage, 'historical_pieces_per_day': round(rate, 2), 'backlog_pieces': load,
                           'conservative_workdays': days})
        available = sum((now.date() + timedelta(days=n)).weekday() != 6 for n in range(1, max(0, (due - now.date()).days) + 1))
        buffer = slots.delivery_buffer_days if slots.delivery_buffer_days is not None else (2 if slots.delivery_point == 'customer' else 0)
        base = sum(s['conservative_workdays'] for s in stages) + buffer
        loss = slots.packing_loss_days or 0
        category = 'ACCESSORIES' if any(word in (slots.product or '').lower() for word in ('scarf', 'beanie')) else 'TOPS'
        workshops = [e for e in self.rows('workshops.csv') if e.record['status'] == 'ACTIVE' and category in e.record['makes']]
        options = [{'workshop_id': e.record['workshop_id'], 'estimated_batch_days': round(float(e.record['current_queue_days']) + float(e.record['pickup_lead_days']) + (slots.quantity or 0) / float(e.record['capacity_pieces_per_day']), 2),
                    'batch_fits': not e.record['max_batch_pieces'] or (slots.quantity or 0) <= int(e.record['max_batch_pieces']),
                    'defect_batch_probability': float(e.record['defect_rate']), 'unit_cost': float(e.record['cost_per_piece'])} for e in workshops]
        worst = {'method': 'serial backlog sum: every active piece at or before each stage is processed before the new order, stage by stage, no overlap',
                 'stages': stages, 'limiting_stage': max(stages, key=lambda s: s['conservative_workdays'])['stage'],
                 'base_required_days': base, 'scenario_required_days': base + loss, 'buffer_days_remaining': available - base - loss,
                 'verdict': 'feasible with conditions' if available >= base + loss else 'not supported',
                 'note': 'Worst case by construction; real lead times are far shorter because stages overlap and most backlog is due before the new order.'}
        # Headline: shared queue simulation with the new order inserted; AFT band for the historical on-time chance.
        try:
            queue = self.new_order_queue(slots, now, due)
        except Exception as exc:  # the queue needs a positive capacity baseline for every stage
            queue = None
            queue_error = str(exc)
        else:
            queue_error = None if queue else 'Insufficient production history for every stage.'
        aft = None
        try:
            from .prediction.aft import LeadTimeModel
            promised = max(1, (due - now.date()).days - (loss + buffer))
            aft = LeadTimeModel().new_order_band(slots.quantity or 0, promised, now.date())
        except Exception as exc:
            aft = {'unavailable': str(exc)}
        verdict = queue['verdict'] if queue else ('feasible with conditions' if available >= base + loss else 'not supported by conservative estimate')
        if queue and (loss or buffer):
            # delivery buffer and lost packing days eat into the queue's slack
            slack = available - buffer - loss - (queue['expected_case']['working_days'] or queue['best_case']['working_days'] or 10 ** 6)
            if slack < 0 and verdict == 'likely':
                verdict = 'tight'
        preliminary = {'likely': 'likely feasible (with stated assumptions)', 'tight': 'tight: feasible only if prioritised or nothing new goes ahead',
                       'unlikely': 'unlikely by this date'}.get(verdict, verdict)
        return {'due_date': due.isoformat(), 'delivery_point': slots.delivery_point, 'available_workdays': available,
                'delivery_buffer_days': buffer, 'packing_loss_days': loss,
                'queue_projection': queue, 'queue_projection_unavailable': queue_error, 'historical_lead_time_model': aft,
                'worst_case_serial_backlog': worst,
                # kept for backward compatibility with earlier narration/tests (now describe the worst case)
                'stages': stages, 'limiting_stage': worst['limiting_stage'], 'base_required_days': base,
                'scenario_required_days': base + loss, 'buffer_days_remaining': available - base - loss,
                'preliminary': preliminary, 'verdict': verdict,
                'assumptions': ['Sundays closed; the new order starts at knitting on the next working day.',
                                'Queue projection: same capacity (previous eight same weekdays x completion factor), earliest-due-date dispatch with manager priorities first, each order at most 60% of a stage per day; expected case adds new orders at the recent arrival rate.',
                                'Historical lead-time model: order size only, 86 completed orders; a chance, not a schedule.',
                                'No per-order WIP quantities: every active order restarts its current stage in full.',
                                f'Delivery buffer: {buffer} working days; ' + ('user supplied.' if slots.delivery_buffer_days is not None else 'unverified planning assumption.'),
                                'Workshop category inferred from product; stage compatibility and availability need confirmation.'],
                'workshop_options': options,
                'recommendation': 'Do not promise an unconditional date. Quote the expected-case date with its assumptions; verify WIP, transport and workshop batch limits first.',
                'limits': 'Forecast scenario, not a confirmed completion date or reserved capacity. Batch defect probability is not an expected defective-piece percentage.'}, active + selected + workshops
