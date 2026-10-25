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


MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
_MONTH_RE = r'(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)'
_DAY_RE = r'(\d{1,2})(?:st|nd|rd|th)?'


def _month_index(word: str) -> int:
    return next(i for i, m in enumerate(MONTHS, 1) if m.startswith(word[:3]))


def parse_day(text: str, now: datetime) -> date | None:
    """'25 March', 'March 25', '25th', '2026-03-25' -> a date in the business year (None when the text is not a date)."""
    t = text.strip().lower().rstrip('.,')
    iso = re.search(r'(\d{4})-(\d{2})-(\d{2})', t)
    if iso:
        return date(int(iso[1]), int(iso[2]), int(iso[3]))     # raises ValueError for 2026-02-31
    m = re.fullmatch(_DAY_RE + r'\s+(' + _MONTH_RE + r')(?:\s+(\d{4}))?', t) or re.fullmatch(r'(' + _MONTH_RE + r')\s+' + _DAY_RE.replace('(\\d{1,2})', '(\\d{1,2})') + r'(?:,?\s+(\d{4}))?', t)
    if m:
        g = m.groups()
        day, month = (int(g[0]), g[1]) if g[0].isdigit() else (int(g[1]), g[0])
        year = int(g[2]) if len(g) > 2 and g[2] else now.year
        return date(year, _month_index(month), day)
    try:
        return resolve_date(t, now)
    except ValueError:
        return None


def resolve_period(text: str, now: datetime, latest: date | None = None) -> dict | None:
    """A date range named in plain words: 'since 25 March', '25 March to 31 March', '25-31 March', 'late March',
    'last week', 'the last three working days', 'in March'. Returns {start, end, label, capped} with the end capped
    to the latest log date, or None when the text names no period (a single date is not a period)."""
    t = text.strip().lower()
    end_cap = latest or (now.date() - timedelta(days=1))
    words = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
    m = re.search(r'(?:the\s+)?(?:last|past|previous)\s+(\d+|' + '|'.join(words) + r')\s+(working|business)?\s*days?', t)
    if m:
        n = int(m[1]) if m[1].isdigit() else words[m[1]]
        day, got, start = end_cap, 0, end_cap
        while got < n and (end_cap - day).days < 60:
            if day.weekday() != 6 or not m[2]:
                got += 1
                start = day
            day -= timedelta(days=1)
        return {'start': start, 'end': end_cap, 'label': f'the last {n} {"working " if m[2] else ""}days ({start.isoformat()} to {end_cap.isoformat()})', 'capped': False}
    if re.search(r'\blast week\b', t):
        monday = now.date() - timedelta(days=now.date().weekday() + 7)
        end = min(monday + timedelta(days=5), end_cap)
        return {'start': monday, 'end': end, 'label': f'last week ({monday.isoformat()} to {end.isoformat()})', 'capped': end < monday + timedelta(days=5)}
    if re.search(r'\bthis week\b', t):
        monday = now.date() - timedelta(days=now.date().weekday())
        return {'start': monday, 'end': end_cap, 'label': f'this week so far ({monday.isoformat()} to {end_cap.isoformat()})', 'capped': False}
    m = re.search(r'\b(early|mid|late)\s+(' + _MONTH_RE + r')\b', t)
    if m:
        month = _month_index(m[2]); year = now.year
        first = date(year, month, 1); last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
        start, end = {'early': (first, date(year, month, 10)), 'mid': (date(year, month, 11), date(year, month, 20)), 'late': (date(year, month, 21), last)}[m[1]]
        end2 = min(end, end_cap)
        return {'start': start, 'end': end2, 'label': f'{m[1]} {MONTHS[month - 1].title()} ({start.isoformat()} to {end2.isoformat()})', 'capped': end2 < end}
    m = re.search(r'\b(?:from\s+)?' + _DAY_RE + r'\s*(' + _MONTH_RE + r')?\s*(?:to|-|–|through|until|till)\s*' + _DAY_RE + r'\s+(' + _MONTH_RE + r')\b', t)
    if m:
        month_b = _month_index(m[4]); month_a = _month_index(m[2]) if m[2] else month_b
        start, end = date(now.year, month_a, int(m[1])), date(now.year, month_b, int(m[3]))
        end2 = min(end, end_cap)
        return {'start': start, 'end': end2, 'label': f'{start.isoformat()} to {end2.isoformat()}', 'capped': end2 < end}
    m = re.search(r'\b(?:since|from|starting|after)\s+(?:the\s+)?(' + _DAY_RE + r'\s+' + _MONTH_RE + r'|' + _MONTH_RE + r'\s+' + _DAY_RE + r'|\d{4}-\d{2}-\d{2})\b', t)
    if m:
        start = parse_day(m[1], now)
        if start:
            if 'after' in m[0]:
                start += timedelta(days=1)
            return {'start': start, 'end': end_cap, 'label': f'since {start.isoformat()} (to {end_cap.isoformat()}, the latest record)', 'capped': False}
    m = re.search(r'\b(?:in|during|for)\s+(' + _MONTH_RE + r')\b(?!\s+\d)', t)
    if m:
        month = _month_index(m[1]); first = date(now.year, month, 1); last = (date(now.year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
        end2 = min(last, end_cap)
        return {'start': first, 'end': end2, 'label': f'{MONTHS[month - 1].title()} ({first.isoformat()} to {end2.isoformat()})', 'capped': end2 < last}
    return None


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
                'change_pct': round(100 * (output / mean(values) - 1)),
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

    def latest_log_date(self) -> date | None:
        dates = [date.fromisoformat(e.record['date']) for e in self.rows('production_log.csv') if e.record['stage'] == 'ASSEMBLY' or True]
        return max(dates) if dates else None

    def stage_band(self, rows: list[Evidence], day: date) -> dict | None:
        """Previous eight same-weekday records before `day` for one stage (the check_normality rule)."""
        base = sorted([e for e in rows if date.fromisoformat(e.record['date']) < day and date.fromisoformat(e.record['date']).weekday() == day.weekday()], key=lambda e: e.record['date'])[-8:]
        if len(base) < 3:
            return None
        values = [int(e.record['pieces_completed']) for e in base]
        return {'min': min(values), 'max': max(values), 'mean': round(mean(values), 1), 'samples': len(values), 'rows': base}

    def stage_comparison(self, target: date, now: datetime) -> tuple[dict[str, Any], list[Evidence]]:
        """Judgement across all four stages on one date: each against its own same-weekday band, ranked by how far
        below the band mean it sits. Falls back to the latest recorded date when the requested one has no record."""
        log = self.rows('production_log.csv')
        latest = self.latest_log_date()
        requested = target
        if not any(e.record['date'] == target.isoformat() for e in log) and latest and target > latest:
            target = latest
        stages = []
        evidence: list[Evidence] = []
        for stage in ('KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING'):
            rows = [e for e in log if e.record['stage'] == stage]
            obs = next((e for e in rows if e.record['date'] == target.isoformat()), None)
            band = self.stage_band(rows, target)
            item = {'stage': stage, 'date': target.isoformat(), 'output': int(obs.record['pieces_completed']) if obs else None}
            if obs:
                evidence.append(obs)
            if band and obs:
                evidence.extend(band['rows'])
                output = item['output']
                item.update(minimum=band['min'], maximum=band['max'], mean=band['mean'], samples=band['samples'],
                            status='below' if output < band['min'] else 'above' if output > band['max'] else 'within',
                            change_pct=round(100 * (output / band['mean'] - 1), 1))
                # consecutive working days below the band up to and including the target
                run = 0
                for e in sorted(rows, key=lambda e: e.record['date'], reverse=True):
                    d0 = date.fromisoformat(e.record['date'])
                    if d0 > target or d0.weekday() == 6:
                        continue
                    b = self.stage_band(rows, d0)
                    if b is None or int(e.record['pieces_completed']) >= b['min']:
                        break
                    run += 1
                item['below_days_running'] = run
            else:
                item.update(status='no_record' if not obs else 'no_baseline')
            stages.append(item)
        ranked = sorted([x for x in stages if x.get('change_pct') is not None], key=lambda x: x['change_pct'])
        worst = ranked[0] if ranked else None
        return {'requested_date': requested.isoformat(), 'date': target.isoformat(), 'weekday': target.strftime('%A'),
                'used_latest_record': target != requested, 'stages': stages,
                'most_off': worst['stage'] if worst and worst['status'] == 'below' else None,
                'ranking': [x['stage'] for x in ranked],
                'baseline': 'each stage against its own previous eight same weekdays (Sundays closed)',
                'limits': 'Descriptive ranges, not control limits; stage outputs are not additive (the same piece passes every stage).'}, evidence

    def production_window(self, period: dict, now: datetime, stage: str | None = None) -> tuple[dict[str, Any], list[Evidence]]:
        """Retrieval + judgement over a date range: the raw rows per day and stage, each day against its same-weekday
        band, the run of days below, and the cumulative shortfall against two stated baselines. Sundays are shown as
        closed. Nothing is summed across stages."""
        log = self.rows('production_log.csv')
        start, end = period['start'], period['end']
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        stages = [stage] if stage else ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING']
        table, evidence = [], []
        per_stage = {}
        for st in stages:
            rows = [e for e in log if e.record['stage'] == st]
            prior = [int(e.record['pieces_completed']) for e in rows if date.fromisoformat(e.record['date']) < start and date.fromisoformat(e.record['date']).weekday() != 6]
            long_mean = round(mean(prior), 1) if len(prior) >= 10 else None
            per_stage[st] = {'stage': st, 'working_days': 0, 'days_below_band': 0, 'total_pieces': 0, 'shortfall_vs_same_weekday_mean': 0.0,
                             'shortfall_vs_prior_working_day_mean': 0.0 if long_mean else None, 'prior_working_day_mean': long_mean,
                             'prior_working_days': len(prior), 'first_below': None, 'last_below': None, 'range_before': (min(prior), max(prior)) if prior else None}
        for day in days:
            row = {'date': day.isoformat(), 'weekday': day.strftime('%a')}
            if day.weekday() == 6:
                row['closed'] = True
                table.append(row); continue
            for st in stages:
                rows = [e for e in log if e.record['stage'] == st]
                obs = next((e for e in rows if e.record['date'] == day.isoformat()), None)
                if not obs:
                    row[st] = None; continue
                evidence.append(obs)
                output = int(obs.record['pieces_completed'])
                band = self.stage_band(rows, day)
                cell = {'pieces': output}
                agg = per_stage[st]
                agg['working_days'] += 1; agg['total_pieces'] += output
                if band:
                    cell.update(band_min=band['min'], band_max=band['max'], band_mean=band['mean'],
                                status='below' if output < band['min'] else 'above' if output > band['max'] else 'within')
                    if cell['status'] == 'below':
                        agg['days_below_band'] += 1
                        agg['first_below'] = agg['first_below'] or day.isoformat(); agg['last_below'] = day.isoformat()
                    agg['shortfall_vs_same_weekday_mean'] = round(agg['shortfall_vs_same_weekday_mean'] + (band['mean'] - output), 1)
                if agg['prior_working_day_mean']:
                    agg['shortfall_vs_prior_working_day_mean'] = round(agg['shortfall_vs_prior_working_day_mean'] + (agg['prior_working_day_mean'] - output), 1)
                row[st] = cell
            table.append(row)
        for agg in per_stage.values():
            agg['every_working_day_below'] = agg['working_days'] > 0 and agg['days_below_band'] == agg['working_days']
            agg['shortfall_vs_same_weekday_mean'] = round(agg['shortfall_vs_same_weekday_mean'])
            if agg['shortfall_vs_prior_working_day_mean'] is not None:
                agg['shortfall_vs_prior_working_day_mean'] = round(agg['shortfall_vs_prior_working_day_mean'])
        return {'period': {'start': start.isoformat(), 'end': end.isoformat(), 'label': period.get('label', ''), 'capped_to_latest_record': period.get('capped', False)},
                'latest_record': (self.latest_log_date() or end).isoformat(), 'rows': table, 'summary': list(per_stage.values()),
                'baselines': {'same_weekday': 'previous eight same weekdays before each day (the normality rule)',
                              'prior_working_day_mean': 'mean of every working day before the period start'},
                'limits': 'Stage outputs are not additive; packing is the closest thing to finished output. The log has no cause, downtime, staffing or team fields.'}, evidence

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

    def find_anomalies(self, slots: Slots, now: datetime) -> tuple[dict[str, Any], list[Evidence]]:
        """Discovery: the ranked list of what is unusual right now, from the same detectors as the alert policy
        (sustained stage drops, stalled customers, near-due misses, overdue, high risk, single low days, idle orders).
        The top five make the answer; the rest are counted. No causes: the data holds none."""
        from .services.alert_policy import detect
        data, evidence = self.queue_snapshot(now)
        alerts = detect(data, now)
        if slots.customer:
            alerts = [a for a in alerts if slots.customer.casefold() in (a.entity + ' ' + a.title).casefold()]
        if slots.stage:
            alerts = [a for a in alerts if a.entity == slots.stage or slots.stage.lower() in a.title.lower()]
        limit = min(max(slots.window_days or 5, 1), 20)
        top = [a.as_dict() for a in alerts[:limit]]
        by_kind: dict[str, int] = {}
        for a in alerts:
            by_kind[a.kind] = by_kind.get(a.kind, 0) + 1
        return {'business_date': now.date().isoformat(), 'findings': top, 'shown': len(top), 'total': len(alerts), 'by_kind': by_kind,
                'rule': 'Ranked by tier (P1 act now, P2 decide today, P3 watch) then score; the same detectors feed the alert policy and the briefing.',
                'limits': 'Findings are patterns in recorded output, dates and queue projections; the log holds no downtime, staffing or cause fields.'}, evidence

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
