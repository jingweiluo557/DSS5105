"""Refit the lead-time model (app/prediction/duration_model.json) from data/orders.csv.

    cd backend && python -m scripts.train_aft_model [--orders ../data/orders.csv] [--today 2026-04-01] [--bootstrap 500]

Needs numpy + scipy (training only; inference in app/prediction/aft.py is pure Python). Maximum-likelihood fit of
ln(lead_days) = a + b*z(pieces) + sigma*N(0,1) on completed orders, with open orders as right-censored observations.
Re-run whenever orders.csv changes; the report lists 95% bootstrap intervals for the three weights.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
MODEL_PATH = HERE.parent / 'app' / 'prediction' / 'duration_model.json'
MIN_COMPLETED = 30


def design(pieces, mean, sd):
    z = (np.asarray(pieces, dtype=float) - mean) / sd
    return np.c_[np.ones(len(z)), z]


def fit(X, T, Xc, c):
    def nll(theta):
        beta, log_s = theta[:-1], theta[-1]
        s = math.exp(log_s)
        ll = (norm.logpdf((np.log(T) - X @ beta) / s) - log_s).sum()
        if len(c):
            ll += norm.logsf((np.log(c) - Xc @ beta) / s).sum()
        return -ll
    start = np.r_[np.linalg.lstsq(X, np.log(T), rcond=None)[0], math.log(0.3)]
    return minimize(nll, start, method='BFGS').x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--orders', type=Path, default=HERE.parent.parent / 'data' / 'orders.csv')
    ap.add_argument('--today', type=str, default=None, help='business date; default = day after the last order/log date')
    ap.add_argument('--bootstrap', type=int, default=500)
    ap.add_argument('--out', type=Path, default=MODEL_PATH)
    a = ap.parse_args()
    rows = list(csv.DictReader(a.orders.open(encoding='utf-8-sig')))
    today = date.fromisoformat(a.today) if a.today else max(date.fromisoformat(r['last_activity_date']) for r in rows)
    comp = [(float(r['pieces']), (date.fromisoformat(r['completed_date']) - date.fromisoformat(r['order_date'])).days) for r in rows if r['status'] == 'COMPLETE' and r['completed_date']]
    comp = [(p, t) for p, t in comp if t > 0]
    opn = [(float(r['pieces']), max((today - date.fromisoformat(r['order_date'])).days, 1)) for r in rows if r['status'] == 'IN_PROGRESS']
    if len(comp) < MIN_COMPLETED:
        raise SystemExit(f'Only {len(comp)} completed orders; need at least {MIN_COMPLETED}.')
    P = np.array([p for p, _ in comp]); T = np.array([t for _, t in comp], dtype=float)
    Pc = np.array([p for p, _ in opn]); C = np.array([c for _, c in opn], dtype=float)
    mean, sd = float(P.mean()), float(P.std(ddof=0))
    theta = fit(design(P, mean, sd), T, design(Pc, mean, sd), C)
    rng = np.random.default_rng(42)
    boots = []
    for _ in range(a.bootstrap):
        i = rng.integers(0, len(P), len(P)); j = rng.integers(0, len(Pc), len(Pc)) if len(Pc) else []
        boots.append(fit(design(P[i], mean, sd), T[i], design(Pc[j], mean, sd), C[j]))
    boots = np.array(boots)
    lo, hi = np.percentile(boots, 2.5, axis=0), np.percentile(boots, 97.5, axis=0)
    params = {'model': 'lognormal_aft_with_censoring', 'version': 'v2', 'target': 'actual lead time in days (completed_date - order_date)',
              'features': ['pieces'], 'intercept': float(theta[0]), 'slope_per_sd_pieces': float(theta[1]), 'sigma': float(math.exp(theta[2])),
              'pieces_mean': mean, 'pieces_sd': sd, 'n_completed': len(comp), 'n_censored': len(opn), 'reference_date': today.isoformat(),
              'ci95': {'intercept': [float(lo[0]), float(hi[0])], 'slope_per_sd_pieces': [float(lo[1]), float(hi[1])], 'sigma': [float(math.exp(lo[2])), float(math.exp(hi[2]))]}}
    a.out.write_text(json.dumps(params, indent=2), encoding='utf-8')
    print(json.dumps(params, indent=2))
    print(f"\nAn average order ({mean:.0f} pieces) takes about {math.exp(theta[0]):.1f} days; each extra {sd:.0f} pieces multiplies lead time by {math.exp(theta[1]):.2f}; same-size orders vary by about ±{100 * math.exp(math.exp(theta[2])) - 100:.0f}% (one sigma).")


if __name__ == '__main__':
    main()
