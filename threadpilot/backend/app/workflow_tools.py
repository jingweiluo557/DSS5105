"""场景 1.1–2.2：刷新 CSV、逐行证据与可解释计算。"""
import csv
import math
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from . import discovery
from .schemas import Evidence, Slots

# One definition of 'normal' for the whole product (briefing, dashboard, chat tools): the previous 8 same weekdays,
# band = mean +/- max(BAND_SD x standard deviation, BAND_MIN_PCT x mean). Kept in step with simulation/briefing.py by a test.
BAND_SD = 1.5
BAND_MIN_PCT = 0.05
STAGES = ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING']


def resolve_datetime(value: str, now: datetime, previous: datetime | None = None) -> datetime | None:
    """场景 3.1/3.3：相对时间归一化；仅有 morning 等模糊时间时返回空。"""
    value = value.strip().lower().replace('.', '')
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


def resolve_date(value: str, now: datetime) -> date:
    """场景 1.5/2.1/2.2：以显式业务时钟解析日期，不偷偷滚动过期日期。"""
    lowered = value.strip().lower()
    if lowered in ('today', '今天'):
        return now.date()
    if lowered in ('yesterday', '昨天'):
        return now.date() - timedelta(days=1)
    if lowered in ('tomorrow', '明天'):
        return now.date() + timedelta(days=1)
    match = re.fullmatch(r'(?:the )?(\d{1,2})(?:st|nd|rd|th)', lowered)
    return now.date().replace(day=int(match[1])) if match else date.fromisoformat(value)


# What this system does not hold. The wording is chosen by plain code from the user's own words, never written by the model, so the
# refusal cannot be talked into inventing a figure. Order matters: the first matching reason wins.
NO_DATA_REASONS = [
    ('modify', re.compile(r'\b(cancel|delete|remove|void|reschedule|reassign|postpone)\b.*\b(order|ord-?\d+)|\b(change|update|edit|move|extend|push back)\b.*\bdue date\b', re.I),
     "I can't cancel, delete or change orders. I only read the data and, after you confirm, record notes, chase-ups and reminders. Nothing was changed."),
    ('price', re.compile(r'\b(revenue|profit|margin|price|prices|pricing|sales|income|turnover|worth|value of)\b', re.I),
     'This system holds no prices, revenue or profit. Orders have pieces, dates and stages only, so any figure would be invented.'),
    ('people', re.compile(r'\b(worker|workers|operator|operators|staff|employee|employees|headcount|shift|shifts|overtime)\b', re.I),
     'No worker names or staffing data are held. Output is recorded per stage per day, not per person.'),
    ('demand', re.compile(r'\b(demand|forecast|next (month|quarter|year)|season)\b', re.I),
     'This chat holds no demand forecast. The dashboard forecasts delay risk for orders already placed, not future sales.'),
]


def explain_no_data(message: str) -> dict[str, str]:
    """What the data cannot answer, and why. Used for out-of-scope questions so the system says so instead of asking an unrelated question."""
    for topic, pattern, reason in NO_DATA_REASONS:
        if pattern.search(message):
            return {'topic': topic, 'reason': reason}
    return {'topic': 'other', 'reason': 'The data holds orders (customer, product, pieces, dates, stage), daily output per stage and workshop profiles. '
                                         'It does not hold what you asked about, so I will not guess.'}


class DataTools:
    def __init__(self, directory: Path) -> None:
        """场景 1.1–2.2：只读取正式数据目录。"""
        self.directory = directory

    def briefing(self) -> dict[str, Any] | None:
        """The newest saved morning briefing. The CSV adapter keeps none, so the caller says so; the database adapter overrides this."""
        return None

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

    def findings(self, now: datetime) -> dict[str, Any]:
        """Tool list_findings (discovery): the ranked findings of the morning-briefing engine, recomputed from current rows."""
        return discovery.findings(self, now.date())

    def risk_levels(self, now: datetime) -> dict[str, dict[str, Any]]:
        """Risk level per in-progress order from the briefing engine's queue projection: one definition of risk for every screen."""
        return discovery.risk_levels(self, now.date())

    def assess_risk(self, order: Evidence, now: datetime, levels: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        """场景 1.3：把已完成迟交、当前逾期和风险判断分别计算。

        The risk LEVEL is the dashboard's projection (overdue / high / medium / low). The review triggers (idle 7+ days, due within 7
        days) are kept as plain facts about what to look at; they are not a second definition of risk."""
        row = order.record
        idle = max(0, (now.date() - date.fromisoformat(row['last_activity_date'])).days)
        due_days = (date.fromisoformat(row['due_date']) - now.date()).days
        complete = row['status'] == 'COMPLETE'
        reasons = []
        if not complete and idle >= 7:
            reasons.append(f'No recorded activity for {idle} days (review threshold: 7 days).')
        if not complete and due_days <= 7:
            reasons.append(f'Due in {due_days} days (review window: 7 days).')
        out = {'order_id': row['order_id'], 'idle_days': idle, 'days_to_due': due_days,
               'overdue': not complete and due_days < 0, 'completed_late': complete and int(row['days_late'] or 0) > 0,
               'review_triggers': reasons, 'review_flag': bool(reasons)}
        if complete:
            out['risk_level'] = 'complete'
        else:
            projection = (self.risk_levels(now) if levels is None else levels).get(row['order_id'])
            if projection:
                out.update(risk_level=projection['level'], risk_reason=projection['reason'], confidence=projection['confidence'],
                           best_finish=projection['best_date'], expected_finish=projection['expected_date'], stalled=projection['stalled'])
            else:
                out.update(risk_level='unknown', risk_reason='Not enough production history to project the queue.')
        out['risk_rule'] = discovery.RISK_RULE
        out['limits'] = ('A risk level is a projection under stated assumptions, not confirmed late delivery. Review triggers say what to look '
                         'at, not how likely it is to be late. No per-order event history or recorded blockers exists in this dataset.')
        return out

    def prioritize(self, slots: Slots, now: datetime) -> tuple[dict[str, Any], list[Evidence]]:
        """场景 1.6：到期窗口包含逾期未完成订单，按截止日、旧更新、ID 排序。"""
        end = now.date() + timedelta(days=slots.window_days or 0)
        rows = [e for e in self.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS'
                and date.fromisoformat(e.record['due_date']) <= end
                and (not slots.customer or e.record['customer'].casefold() == slots.customer.casefold())]
        rows.sort(key=lambda e: (e.record['due_date'], e.record['last_activity_date'], e.record['order_id']))
        levels = self.risk_levels(now)
        return {'window_end': end.isoformat(), 'rule': 'Earlier due date first; ties: older last activity, then order ID. Includes overdue active orders. No opaque score.',
                'orders': [self.assess_risk(e, now, levels) for e in rows]}, rows

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
        centre = mean(values)
        spread = pstdev(values)
        half = max(BAND_SD * spread, BAND_MIN_PCT * centre)   # the one definition of normal, shared with the morning briefing
        low, high = centre - half, centre + half
        return {'stage': slots.stage, 'date': target.isoformat(), 'output': output,
                'observation_source': provenance, 'user_observation': slots.observed_output,
                'sample_count': len(values), 'baseline': 'previous eight same weekdays, excluding target and future dates',
                'rule': 'normal band = mean +/- max(1.5 x standard deviation, 5% of the mean)',
                'minimum': min(values), 'maximum': max(values), 'mean': round(centre, 2), 'standard_deviation': round(spread, 2),
                'band_low': round(low, 1), 'band_high': round(high, 1),
                'status': 'below' if output < low else 'above' if output > high else 'within',
                'limits': 'Descriptive historical band, not a statistical control limit. One low observation alone is not proof of a sustained problem.'}, baseline + observed

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

    def capacity(self, slots: Slots, now: datetime) -> tuple[dict[str, Any], list[Evidence]]:
        """场景 1.5：以历史产量和在制订单做保守串行估算及损失日情景。"""
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
        return {'due_date': due.isoformat(), 'delivery_point': slots.delivery_point, 'available_workdays': available,
                'stages': stages, 'limiting_stage': max(stages, key=lambda s: s['conservative_workdays'])['stage'],
                'base_required_days': base, 'packing_loss_days': loss, 'scenario_required_days': base + loss,
                'buffer_days_remaining': available - base - loss,
                'preliminary': 'feasible with conditions' if available >= base + loss else 'not supported by conservative estimate',
                'assumptions': ['Sundays closed; start next business day.', 'Historical throughput is a proxy, not reserved capacity.',
                                'All outstanding quantities remain at their current and later stages; no per-order WIP quantities available.',
                                'Conservative serial stages, no pipeline overlap; full current backlog ahead of the new order.',
                                f'Delivery buffer: {buffer} working days; ' + ('user supplied.' if slots.delivery_buffer_days is not None else 'unverified planning assumption.'),
                                'Workshop category inferred from product; stage compatibility and availability need confirmation.'],
                'workshop_options': options,
                'recommendation': 'Do not promise an unconditional date. Verify WIP, reserved capacity, transport and workshop batch limits; offer a later date if constraints cannot be cleared.',
                'limits': 'Forecast scenario, not a confirmed completion date. Batch defect probability is not an expected defective-piece percentage.'}, active + selected + workshops
