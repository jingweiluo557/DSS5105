"""How many numbers does the system state that no tool produced? The invented-number rate, measured on every answer.

The brief calls a fabricated number the worst failure in this track. Saying "the model never does the arithmetic" is a design
claim; this script measures it. For every question it asks, it records what each tool returned (by wrapping the dashboard
chat's tools in the page) and checks every number in the answer the manager reads (not the expandable detail) against them:

    traced     the number is in a tool result (exact, or the same value with commas, rounding or sign removed), is how many
               items a tool returned (e.g. "8 orders are late" from a list of 8), or is the total of one result's numbers
    echoed     the number (or date) was in the manager's own question
    date       part of a date that is in a tool result or is the business date
    product    a fixed rule of the product, in its own words ("07:00", "15 minutes", "previous 8 same weekdays", "within 7 days"...)
    UNTRACED   none of the above: listed one by one and read by hand

    python -m evaluation.provenance                 # main 36, held-out 21 and the 16 bait questions on the dashboard chat
    python -m evaluation.provenance --save          # also writes evaluation/results/provenance.json (the latest run)
    (the first run, before any fix, is kept as evaluation/results/provenance_first_run.json)

The bait questions (evaluation/bait_questions.json) are also scored for behaviour with the usual checks. They were written and
committed before the first run, and that first run is what docs/evaluation.md reports.

Limits: a traced number can still be the wrong number from the right tool (accuracy is what the 36 questions measure); the
check only proves it was not made up. The live backend's answers are also assembled by code from tool results; its SQL agent
(B14) is the one place a model writes the words, and it is not wired to the chat page (docs/tool_boundaries.md).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from .score import load_questions, markdown, score, summary

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).parent
BUSINESS_DATE = date(2026, 4, 1)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
# Fixed rules of the product that answers may state, matched as whole phrases so a bare small number is never waved through.
PRODUCT = re.compile(r"\b(?:07:00|7 ?a\.?m\.?|15 minutes|(?:previous|last) 8 same weekdays|8 same-weekday|within 7 days|next 7 days|"
                     r"(?:5|five)\+? working days|top 5|12 working days|(?:last|past|previous) (?:30|60) days|30 days before|"
                     r"stage \d of 4|4 stages|1\.5 (?:SD|standard deviations?)|3[- ]sigma|5% of the mean)\b", re.I)

JS_ASK = """(turns) => {
  go(0); ThreadPilotChat.reset();
  const out = [];
  const T = ThreadPilotChat.tools;
  for (const t of turns) {
    const seen = [];
    const saved = {};
    for (const [name, tool] of Object.entries(T)) { saved[name] = tool.run; tool.run = a => { const r = saved[name](a); seen.push({name, result: r}); return r; }; }
    let r;
    try { r = ThreadPilotChat.respond(t); } finally { for (const [name, fn] of Object.entries(saved)) T[name].run = fn; }
    out.push({answer: r.lines.join(' '), results: JSON.stringify(seen, (k, v) => (typeof v === 'function' ? undefined : v))});
  }
  return out;
}"""


def ask_all(questions: list[dict]) -> dict[str, dict]:
    from playwright.sync_api import sync_playwright
    html = Path(tempfile.mkdtemp()) / "demo.html"
    subprocess.run([sys.executable, "-m", "simulation.render_demo", "--days", "14", "--briefings", str(html.parent / "b"), "--html", str(html)],
                   cwd=ROOT, check=True, capture_output=True)
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html.as_uri())
        for q in questions:
            turns = page.evaluate(JS_ASK, q["turns"])
            last = turns[-1]
            out[q["id"]] = {"answer": re.sub(r"<[^>]+>", "", last["answer"]), "results": last["results"], "question": " ".join(q["turns"])}
        browser.close()
    return out


# ---------------------------------------------------------------- the check
NUMBER = re.compile(r"(?<![\w-])-?\d[\d,]*(?:\.\d+)?")
DATE_DM = re.compile(r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", re.I)
DATE_MD = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{1,2})\b", re.I)
ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
ORDER_ID = re.compile(r"\bORD-\d+\b")
TIME = re.compile(r"\b\d{1,2}:\d{2}\b")


def atoms(results_json: str) -> tuple[set[str], set[str]]:
    """Every number a tool returned, in the forms an answer may print it, and every ISO date it returned."""
    nums: set[str] = set()
    data = json.loads(results_json)

    def add(v: float) -> None:
        for x in (v, abs(v)):
            nums.add(f"{x:g}")
            nums.add(str(round(x)))
            nums.add(f"{round(x, 1):g}")

    def walk(o) -> None:
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float)):
            add(float(o))
        elif isinstance(o, str):
            for m in NUMBER.finditer(o.replace(",", "")):
                try:
                    add(float(m.group()))
                except ValueError:
                    pass
        elif isinstance(o, list):
            nums.add(str(len(o)))
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            values = [v for v in o.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if len(values) >= 2:          # a total the answer adds up in code, e.g. 8 late + 26 at risk + 0 on track = 34
                add(float(sum(values)))
            for x in o.values():
                walk(x)
    walk(data)
    return nums, {"-".join(m) for m in ISO.findall(results_json)}


def check(answer: str, question: str, results_json: str) -> dict:
    nums, dates = atoms(results_json)
    dates = set(dates) | {BUSINESS_DATE.isoformat()}
    asked = {m.group().replace(",", "") for m in NUMBER.finditer(question)}
    text = ORDER_ID.sub(" ", answer)
    found = {"traced": 0, "echoed": 0, "date": 0, "product": 0, "untraced": []}
    found["product"] = len(PRODUCT.findall(text))
    text = PRODUCT.sub(" ", text)

    def date_ok(day: int, mon: str) -> bool:
        try:
            iso = date(2026, MONTHS[mon[:3].lower()], day).isoformat()
        except ValueError:
            return False
        return iso in dates or any(d.startswith(iso[:7]) for d in dates)

    for m in list(DATE_DM.finditer(text)) + list(DATE_MD.finditer(text)):
        day, mon = (int(m.group(1)), m.group(2)) if m.re is DATE_DM else (int(m.group(2)), m.group(1))
        other_year = [d for d in dates if d[4:] == f"-{MONTHS[mon[:3].lower()]:02d}-{day:02d}" and not d.startswith("2026")]
        if date_ok(day, mon):
            found["date"] += 1
        elif other_year:                  # the tool worked on the same day and month in another year: say so, never wave it through
            found["untraced"].append(f"{m.group()} (the tool used {other_year[0]})")
        elif re.search(rf"\b{day}(?:st|nd|rd|th)?\s+(?:of\s+)?{mon[:3]}|\b{mon[:3]}[a-z]*\s+{day}\b", question, re.I):
            found["echoed"] += 1
        else:
            found["untraced"].append(m.group())
        text = text.replace(m.group(), " ", 1)
    for m in ISO.finditer(text):
        if m.group() in dates:
            found["date"] += 1
        else:
            found["untraced"].append(m.group())
    text = ISO.sub(" ", text)
    for m in TIME.finditer(text):
        found["untraced"].append(m.group())
    text = TIME.sub(" ", text)
    for m in NUMBER.finditer(text):
        raw = m.group().replace(",", "").lstrip("-")
        value = f"{float(raw):g}"
        if raw in asked or value in asked:
            found["echoed"] += 1
        elif value in nums or raw in nums:
            found["traced"] += 1
        else:
            found["untraced"].append(m.group())
    return found


def run(sets: dict[str, list[dict]]) -> dict:
    report = {"sets": {}, "untraced": []}
    for name, questions in sets.items():
        got = ask_all(questions)
        totals = {"answers": len(questions), "numbers": 0, "traced": 0, "echoed": 0, "date": 0, "product": 0, "untraced": 0}
        for q in questions:
            c = check(got[q["id"]]["answer"], got[q["id"]]["question"], got[q["id"]]["results"])
            for k in ("traced", "echoed", "date", "product"):
                totals[k] += c[k]
            totals["untraced"] += len(c["untraced"])
            totals["numbers"] += sum(c[k] for k in ("traced", "echoed", "date", "product")) + len(c["untraced"])
            for u in c["untraced"]:
                report["untraced"].append({"set": name, "id": q["id"], "number": u, "answer": got[q["id"]]["answer"][:400]})
        report["sets"][name] = totals
        if name == "bait":
            results = score(questions, {k: v["answer"] for k, v in got.items()})
            report["bait"] = {"summary": summary(results), "results": results}
    return report


def main() -> int:
    sets = {"main": load_questions(), "heldout": load_questions(HERE / "heldout_questions.json"),
            "bait": load_questions(HERE / "bait_questions.json")}
    r = run(sets)
    print("| Set | Answers | Numbers stated | Traced to a tool | Dates | Echoed from the question | Product facts | Untraced |")
    print("|---|---|---|---|---|---|---|---|")
    for name, t in r["sets"].items():
        print(f"| {name} | {t['answers']} | {t['numbers']} | {t['traced']} | {t['date']} | {t['echoed']} | {t['product']} | {t['untraced']} |")
    for u in r["untraced"]:
        print(f"\nUNTRACED {u['set']} {u['id']}: {u['number']}\n    {u['answer'][:300]}")
    print("\n" + markdown(r["bait"]["results"], "Bait questions, first pass" if "--first-pass" in sys.argv else "Bait questions (not first pass)"))
    for x in r["bait"]["results"]:
        if not x["passed"]:
            print(f"\nFAIL {x['id']} [{x['category']}] {x['question']}\n     {x['answer'][:300]}")
    if "--save" in sys.argv:            # the first run was saved as provenance_first_run.json; this file is the latest run
        (HERE / "results" / "provenance.json").write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
