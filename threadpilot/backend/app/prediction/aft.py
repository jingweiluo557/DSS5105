"""Lead-time model for Judgement tools: log-normal accelerated-failure-time (AFT) regression with censoring.

    ln(lead_days) = intercept + slope * z(pieces) + sigma * N(0, 1),   z = (pieces - mean) / sd

The three weights live in duration_model.json (fitted by scripts/train_aft_model.py on the 86 completed orders,
with the 34 open orders as right-censored observations; see docs/PREDICTION_MODEL.md). Inference here needs no
numpy/scipy so the cloud function stays light; the normal CDF uses math.erf and the inverse CDF a standard
rational approximation (Acklam), accurate to ~1e-9, far below the model's own uncertainty.

What this module deliberately does not do: it never reads the production stage (orders carry no stage-entry
dates), never uses customer identity (7 extra parameters on 86 orders), and never returns a number for an order
it cannot find or that is already complete.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

MODEL_PATH = Path(__file__).with_name('duration_model.json')
HIGH, MEDIUM = 0.60, 0.35
LATE_OFFSET = 0.5  # lead times are whole days: late means T >= planned + 1, i.e. T > planned + 0.5

LIMITATIONS = [
    'Only order size is used; the current production stage is not, because the data has no stage-entry history.',
    'Fitted on 86 completed orders: probabilities are a ranking, not exact odds (0.4-0.6 scores were late about 26% of the time in validation).',
    'Category, product, promised lead time, backlog and order month added no reliable accuracy and are not used.',
]


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _phi_inv(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation, |error| < 1.2e-9)."""
    p = min(max(p, 1e-12), 1 - 1e-12)
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - 0.02425:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


class LeadTimeModel:
    def __init__(self, params: dict | None = None, path: Path = MODEL_PATH) -> None:
        self.params = params or json.loads(path.read_text(encoding='utf-8'))
        p = self.params
        self.intercept, self.slope, self.sigma = float(p['intercept']), float(p['slope_per_sd_pieces']), float(p['sigma'])
        self.mean, self.sd = float(p['pieces_mean']), float(p['pieces_sd'])

    # ---- distribution of the lead time T (days) for an order of `pieces` pieces
    def mu(self, pieces: float) -> float:
        return self.intercept + self.slope * (float(pieces) - self.mean) / self.sd

    def survival(self, pieces: float, t: float) -> float:
        """P(T > t)."""
        return 1 - _phi((math.log(max(t, 1e-9)) - self.mu(pieces)) / self.sigma)

    def typical_lead_days(self, pieces: float) -> float:
        return math.exp(self.mu(pieces))

    def prob_late(self, pieces: float, planned_days: float, elapsed_days: float | None = None) -> float:
        """P(lead > planned), or conditional on the order still being open after elapsed_days; 1.0 once past due."""
        threshold = planned_days + LATE_OFFSET
        p = self.survival(pieces, threshold)
        if elapsed_days is not None:
            if elapsed_days >= threshold:
                return 1 - 1e-4
            p = min(p / max(self.survival(pieces, elapsed_days), 1e-12), 1.0)
        return min(max(p, 1e-4), 1 - 1e-4)

    def conditional_quantile(self, pieces: float, elapsed_days: float, u: float) -> float:
        """Lead time t with P(T > t | T > elapsed) = u; u = 0.5 is the conditional median."""
        mu = self.mu(pieces)
        z_elapsed = (math.log(max(elapsed_days, 1e-9)) - mu) / self.sigma
        tail = min(max(u * (1 - _phi(z_elapsed)), 1e-12), 1 - 1e-12)
        return math.exp(mu + self.sigma * _phi_inv(1 - tail))

    @staticmethod
    def level(p: float) -> str:
        return 'HIGH' if p >= HIGH else 'MEDIUM' if p >= MEDIUM else 'LOW'

    def describe(self) -> dict:
        p = self.params
        return {'name': 'log-normal AFT with censoring', 'formula': 'ln(lead_days) = intercept + slope * z(pieces) + sigma * N(0,1)',
                'intercept': round(self.intercept, 4), 'slope_per_sd_pieces': round(self.slope, 4), 'sigma': round(self.sigma, 4),
                'pieces_mean': round(self.mean, 1), 'pieces_sd': round(self.sd, 1),
                'fitted_on': f"{p.get('n_completed')} completed + {p.get('n_censored')} open orders, reference date {p.get('reference_date')}",
                'validation': '5x10 cross-validation: AUC 0.90, accuracy 81% (base rate 61%), finish-date MAE 4.5 days, 80% interval coverage 78-84%'}

    # ---- order-level forecast
    def forecast_order(self, record: dict, today: date) -> dict:
        """Delay probability, level and completion-date range for one IN_PROGRESS order record (CSV field names)."""
        pieces = float(record['pieces'])
        order_date, due = date.fromisoformat(record['order_date']), date.fromisoformat(record['due_date'])
        planned = float((due - order_date).days)
        elapsed = float(max((today - order_date).days, 0))
        p = self.prob_late(pieces, planned, elapsed)
        med = self.conditional_quantile(pieces, elapsed, 0.5)
        lo = self.conditional_quantile(pieces, elapsed, 0.9)
        hi = self.conditional_quantile(pieces, elapsed, 0.1)
        to_date = lambda lead: (order_date + timedelta(days=int(round(lead)))).isoformat()
        return {'order_id': record['order_id'], 'delay_probability': round(p, 3), 'risk_level': self.level(p),
                'already_past_due': today > due, 'due_date': due.isoformat(), 'order_date': order_date.isoformat(),
                'elapsed_days': int(elapsed), 'planned_lead_days': int(planned), 'days_to_due': (due - today).days,
                'expected_completion_date': to_date(med), 'completion_range_80pct': [to_date(lo), to_date(hi)],
                'expected_days_after_due': int(round(max(0.0, med - planned))),
                'typical_lead_days_for_this_size': round(self.typical_lead_days(pieces), 1), 'pieces': int(pieces),
                'model': self.describe(),
                'calculation': {'delay_probability': 'P(T > planned + 0.5 | T > elapsed) = S(planned + 0.5) / S(elapsed); 1.0 once past due',
                                'expected_completion_date': 'order_date + conditional median lead time', 'completion_range_80pct': 'conditional 10th-90th percentile',
                                'risk_level': f'HIGH >= {HIGH}, MEDIUM >= {MEDIUM}, else LOW'},
                'assumptions': ['Lead time depends on order size only; log-normal with constant spread.', 'The order keeps being processed at the historical pace.'],
                'limitations': LIMITATIONS}

    # ---- new-order feasibility band
    def new_order_band(self, pieces: float, promised_days: float, today: date) -> dict:
        """For an order placed today: chance of finishing within promised_days, and the lead time we could promise with 80% confidence."""
        p_on_time = 1 - self.prob_late(pieces, promised_days)
        t80 = math.exp(self.mu(pieces) + self.sigma * _phi_inv(0.8))
        t50 = self.typical_lead_days(pieces)
        return {'pieces': int(pieces), 'promised_lead_days': int(promised_days), 'p_on_time': round(p_on_time, 3),
                'typical_lead_days': round(t50, 1), 'lead_days_80pct_confidence': int(math.ceil(t80)),
                'earliest_date_80pct_confidence': (today + timedelta(days=int(math.ceil(t80)))).isoformat(),
                'basis': 'historical lead times of orders of this size, not current queue load', 'limitations': LIMITATIONS}
