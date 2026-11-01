"""Why "normal" is the previous 8 same weekdays: the measured reasons, in words the manager can read.

The figures come from analysis/baseline_window.py (docs/BASELINE_WINDOW.md), the product's own rules run on this factory's
data. They are copied here because the backend ships without the analysis folder; tests/test_sprint3.py checks that they
still match analysis/results/baseline_window.json, so a re-run that changes them fails the build until they are updated.
"""
from __future__ import annotations

import re

# K same weekdays -> false P1 alerts a month (4 stages), normal days flagged "below range" a month, share of 5-day 20% drops
# that raise the alert, stage-days of the 90-day log with a full K-week baseline (of 236 judged)
STUDY = {
    4: {'false_alerts': 0.67, 'below_range_days': 19.8, 'small_drops_caught': 91, 'full_baseline_days': 212},
    6: {'false_alerts': 0.21, 'below_range_days': 13.8, 'small_drops_caught': 85, 'full_baseline_days': 164},
    8: {'false_alerts': 0.1, 'below_range_days': 10.6, 'small_drops_caught': 83, 'full_baseline_days': 116},
    10: {'false_alerts': 0.06, 'below_range_days': 8.5, 'small_drops_caught': 80, 'full_baseline_days': 68},
    12: {'false_alerts': 0.03, 'below_range_days': 7.0, 'small_drops_caught': 74, 'full_baseline_days': 20},
}
JUDGED_STAGE_DAYS = 236

QUESTION = re.compile(
    r"\bwhy\b[^?.]*\b(?:8|eight)\b[^?.]*\b(?:weeks?|weekdays?|days?|records?|samples?|baseline|tuesdays|mondays|wednesdays|thursdays|fridays|saturdays)\b"
    r"|^\s*why (?:8|eight)\s*[?.!]*\s*$"
    r"|\bwhy\b[^?.]*\bsame[- ]weekdays?\b"
    r"|\bwhy\b[^?.]*\bnot\b[^?.]*\b(?:(?:7|seven|4|four|6|six|10|ten|12|twelve)\s*(?:days?|weeks?|weekdays?)|last week|a week|one week|average of the last)\b"
    r"|\bhow\b[^?.]*\b(?:choose|chose|pick|picked|decide|decided)\b[^?.]*\b(?:baseline|eight|8|window|normal)\b"
    r"|\bwhy\b[^?.]*\b(?:that|this|your) (?:baseline|window|definition of normal)\b", re.I)


def asks_why(message: str) -> bool:
    return bool(QUESTION.search(message))


def answer() -> str:
    s = STUDY
    return (
        "Why “normal” is the previous 8 same weekdays:\n"
        "- Same weekday: the factory is closed on Sundays and each weekday runs at its own level. A “last 7 days” average would count a closed day and, "
        "during a problem, average the problem itself, so a drop would start to look normal.\n"
        f"- Eight weeks, measured on this factory's data with the alert rules this system uses: with 4 weeks you would get about {s[4]['false_alerts']} false alert emails a month "
        f"and {s[4]['below_range_days']:.0f} normal days a month flagged “below range”; with 8 weeks about {s[8]['false_alerts']} a month (roughly one a year across all four stages) "
        f"and {s[8]['below_range_days']:.0f} days, while every 30% drop is still caught on its third day and {s[8]['small_drops_caught']}% of 5-day 20% drops.\n"
        f"- More weeks buys little: 10–12 weeks cut false alerts only to {s[10]['false_alerts']}–{s[12]['false_alerts']} a month, miss more small drops "
        f"({s[10]['small_drops_caught']}–{s[12]['small_drops_caught']}% caught), and on 90 days of history only {s[10]['full_baseline_days']}–{s[12]['full_baseline_days']} of "
        f"{JUDGED_STAGE_DAYS} stage-days would have a full baseline (8 weeks: {s[8]['full_baseline_days']}).\n"
        "- So 8 is the middle of a flat optimum: 6 to 10 weeks behave alike. Eight same weekdays span about two months. "
        "No planner has checked the flagged days against days they remember as bad yet; that is the next validation. "
        "Full study: docs/BASELINE_WINDOW.md.")
