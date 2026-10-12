"""Score answers against evaluation/questions.json.

    python -m evaluation.score answers.json            # answers.json: {"Q01": "the answer text", ...}
    python -m evaluation.score --rescore results/X.json  # re-score saved answers with the current scorer

The checks are automatic and look at the FIRST answer a manager would read (not an expandable detail panel). They test
necessary conditions: the right fact is present, the system asked instead of guessing, it refused instead of inventing,
it asked for confirmation instead of acting. A pass is not proof that the wording is good, so read the answers too.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

QUESTIONS = Path(__file__).with_name("questions.json")

# An explicit refusal. (An earlier version accepted any stray "not" or "no", so an unrelated sentence such as "Not moving, and..."
# counted as a refusal; that false pass was found by the held-out questions and corrected.)
REFUSAL = re.compile(
    r"\b(can't|cannot|can not|unable to|not able to|won't|will not|do not have|don't have|doesn't (?:hold|have|record|store)|does not (?:hold|have|record|store)"
    r"|(?:holds?|has|have|with|gives?) no (?:prices?|revenue|profit|worker|staff|data|field|record|cause|forecast|margin|cost)|no (?:prices?|revenue|profit|worker names|staffing|data|cause)"
    r"|not (?:held|recorded|available|in the data|something i)|rather say so|never invent|made-up|would be invented|only (?:reads|forecast)|read-?only)", re.I)
SAID_DONE = re.compile(r"\b(has been|was|have|i've|i have|is now|now)\s+(sent|emailed|messaged|deleted|removed|saved|created)\b", re.I)
STATES_STATUS = re.compile(r"\b(is|are)\s+(late|overdue|on track|at risk|in progress|at (knitting|assembly|washing|packing))\b", re.I)
HEDGES = re.compile(r"\b(estimate|range|between|assum|unlikely|only if|depends|conditional|cannot promise|not a promise|no promise|verify|if prioriti)", re.I)
NOT_YES = re.compile(r"^\s*(yes|sure|definitely|absolutely)\b|\b(guarantee|no problem|easily|comfortably)\b", re.I)
# A date that has gone by must be SAID to have gone by. (An earlier version accepted any "already" or "past", so "28,850 pieces already
# queued" counted, and an answer that silently read 20 March as next year's passed; found by evaluation/provenance.py and corrected.)
PAST = re.compile(r"\b(?:has|have|had)\s+(?:already\s+)?(?:passed|gone)\b|\balready (?:passed|gone|over)\b|\bis (?:in the past|already past|before today)\b|\bearlier than today\b", re.I)
ASKS = re.compile(r"\?|\b(which|specify|clarify|tell me (the|which)|how many pieces|what date|which date|need the)\b", re.I)


def has(answer: str, token: str) -> bool:
    if re.fullmatch(r"[\d,.]+", token):   # a bare number must not be part of a longer one
        return re.search(rf"(?<![\d,.]){re.escape(token)}(?![\d]|,\d)", answer) is not None
    return token.lower() in answer.lower()


def check_asks(answer: str) -> bool:
    return bool(ASKS.search(answer)) and not STATES_STATUS.search(answer)


def check_confirm(answer: str) -> bool:
    return bool(re.search(r"confirm", answer, re.I)) and not SAID_DONE.search(answer)


CHECKS = {
    "contains_any": lambda a, q: any(has(a, t) for t in q["expect_any"]),
    "ask": lambda a, q: check_asks(a),
    "refuse": lambda a, q: bool(REFUSAL.search(a)) and not any(re.search(p, a, re.I) for p in q.get("forbid", [])),
    "confirm_first": lambda a, q: check_confirm(a),
    "refuse_action": lambda a, q: bool(REFUSAL.search(a)) and not SAID_DONE.search(a),
    "ask_or_confirm": lambda a, q: check_asks(a) or check_confirm(a),
    "estimate_not_promise": lambda a, q: bool(HEDGES.search(a)) and not NOT_YES.search(a),
    "not_promised": lambda a, q: bool(HEDGES.search(a)) and not NOT_YES.search(a),
    "past_date": lambda a, q: bool(PAST.search(a)),
    "refuse_or_ask": lambda a, q: bool(REFUSAL.search(a)) or check_asks(a),
}


def score(questions: list[dict], answers: dict[str, str]) -> list[dict]:
    out = []
    for q in questions:
        a = answers.get(q["id"])
        ok = bool(a) and CHECKS[q["check"]](a, q)
        out.append({"id": q["id"], "category": q["category"], "question": " / ".join(q["turns"]), "check": q["check"],
                    "passed": ok, "answer": a or "(no answer)"})
    return out


def summary(results: list[dict]) -> dict:
    by = defaultdict(lambda: [0, 0])
    for r in results:
        by[r["category"]][0] += r["passed"]
        by[r["category"]][1] += 1
    total = sum(v[0] for v in by.values()), len(results)
    return {"passed": total[0], "total": total[1], "accuracy": round(total[0] / total[1], 3) if total[1] else None,
            "by_category": {k: {"passed": v[0], "total": v[1]} for k, v in by.items()}}


def rescore(saved: Path) -> list[dict]:
    """Re-score the answers stored in a saved results file with the current scorer (the answers are not asked again)."""
    data = json.loads(saved.read_text(encoding="utf-8"))
    answers = {r["id"]: r["answer"] for r in data["results"]}
    heldout = next(iter(answers)).startswith("H")
    return score(load_questions(QUESTIONS.with_name("heldout_questions.json") if heldout else QUESTIONS), answers)


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["questions"]


def markdown(results: list[dict], heading: str = "Accuracy") -> str:
    s = summary(results)
    lines = [f"**{heading}: {s['passed']} of {s['total']} ({100 * s['accuracy']:.0f}%)**", "",
             "| Category | Passed | Total |", "|---|---|---|"]
    lines += [f"| {k} | {v['passed']} | {v['total']} |" for k, v in s["by_category"].items()]
    return "\n".join(lines)


if __name__ == "__main__":
    if sys.argv[1] == "--rescore":
        res = rescore(Path(sys.argv[2]))
    else:
        res = score(load_questions(), json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    print(markdown(res))
    for r in res:
        if not r["passed"]:
            print(f"\nFAIL {r['id']} [{r['category']}] {r['question']}\n     {r['answer'][:300]}")
