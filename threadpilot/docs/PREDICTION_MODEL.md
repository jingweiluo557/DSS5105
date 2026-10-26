# Lead-time prediction model (Judgement tools)

Version 2 · snapshot 2026-04-01 (120 orders) · weights in `backend/app/prediction/duration_model.json` · inference `backend/app/prediction/aft.py` (pure Python) · training `backend/scripts/train_aft_model.py` (numpy + scipy).

## What it is

A log-normal accelerated-failure-time (AFT) regression with right-censoring: survival analysis for lead times. It predicts the *distribution* of an order's lead time in days and derives from it the delay probability, the expected completion date and an 80% range. One input, three weights:

```
ln(lead_days) = 3.162 + 0.245 · z(pieces) + 0.225 · noise,   z = (pieces − 705) / 521,   noise ~ N(0, 1)
```

| Weight | Value (95% bootstrap range) | Plain meaning |
|---|---|---|
| intercept | 3.162 (3.118–3.210) | an average order (705 pieces) takes about 23.6 days |
| slope per SD of pieces | 0.245 (0.204–0.286) | each extra 521 pieces multiplies lead time by 1.28 (≈ +4.8% per 100 pieces) |
| sigma | 0.225 (0.192–0.256) | same-size orders vary by about ±25% |

Fitted by maximum likelihood on the 86 completed orders (lead time = completed_date − order_date); the 34 open orders enter as "at least this long so far" (censoring) instead of being discarded. Intervals from 500 bootstrap refits.

## How the chat uses it

| Tool | Input | Output | Deliberately does not |
|---|---|---|---|
| `predict_order_delay` (intent `order.forecast`) | one IN_PROGRESS order ID | P(late) given the order is still open after *e* days = S(planned + 0.5)/S(e), 1.0 once past due; level HIGH ≥ 0.60 / MEDIUM ≥ 0.35 / LOW; expected completion = order_date + conditional median; 80% range = conditional P10–P90 | use the current stage (no stage-entry dates exist), use customer identity, forecast completed orders |
| `estimate_capacity` → `historical_lead_time_model` | quantity and promised lead days of a NEW order | P(on time) for an order of that size placed today; lead time we could promise with 80% confidence | replace the queue simulation: it is a size-based prior, the queue gives the date |

Every result carries `assumptions`, `limitations` and the model description, so the narrator quotes caveats rather than guesses.

## Validation (orders the model had not seen; `validate_model.py` in the original tool zip)

| Check | Result |
|---|---|
| Late vs on-time at order acceptance, 5-fold CV × 10 | AUC 0.904, accuracy 81% (always "on time": 61%), Brier 0.128 (constant: 0.239) |
| Still open after 50% / 80% of the promised lead | AUC 0.89 / 0.82 |
| Expected finish date | MAE 4.5 days (typical-lead-time baseline: 6.5) |
| 80% date range | contains the real date 78–84% of the time |
| Calibration | reliable at the ends; 0.4–0.6 scores were late only ~26% of the time, so present levels as a ranking |

## Ideas tested and not used (numbers in the zip's `excluded_ideas_report.json`)

| Idea | Why not |
|---|---|
| Logistic regression late/not-late (the earlier prototype in `DSS5105_predict/`) | label only, no dates, not time-aware; 81% accuracy, no better |
| Random forest | 86 orders and one useful input: nothing to learn, no interpretable weights |
| Category, product, promised lead, backlog, month | no reliable CV gain; backlog and month point the wrong way |
| Customer identity | small gain (MAE 4.5 → 4.0) but 7 parameters on 86 orders; candidate for the next retrain |
| Next customer / next product | no signal (AUC 0.58; 13–20% vs 14% chance) |
| Workshop-capacity dates | 13–18 days too early (counts sewing only) |
| Production stage | orders record only the current stage, never when it was entered |

Retrain with `python -m scripts.train_aft_model` whenever `orders.csv` grows; the script prints the new weights and their ranges.
