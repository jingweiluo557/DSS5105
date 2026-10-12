"""Ask every evaluation question to the dashboard chat (no server, no API key) and score the answers.

    python -m evaluation.run_dashboard                      # prints the table and the failures
    python -m evaluation.run_dashboard --save first_run     # also writes evaluation/results/first_run.json
    python -m evaluation.run_dashboard --heldout            # the 20 held-out questions instead of the main 36
    add --first-pass to label the figure "First-pass accuracy" (use it only for the very first run of a set)

The page is opened on 1 April 2026 (the provided data) and each question starts a fresh conversation, except multi-turn ones.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .score import load_questions, markdown, score, summary

ROOT = Path(__file__).resolve().parents[1]


def ask_all(questions: list[dict]) -> dict[str, str]:
    from playwright.sync_api import sync_playwright
    html = Path(tempfile.mkdtemp()) / "demo.html"
    subprocess.run([sys.executable, "-m", "simulation.render_demo", "--days", "14", "--briefings", str(html.parent / "b"), "--html", str(html)],
                   cwd=ROOT, check=True, capture_output=True)
    answers = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html.as_uri())
        for q in questions:
            texts = page.evaluate("""(turns) => { go(0); ThreadPilotChat.reset();
                return turns.map(t => { const r = ThreadPilotChat.respond(t); return r.lines.join(' '); }); }""", q["turns"])
            answers[q["id"]] = re.sub(r"<[^>]+>", "", texts[-1])
        browser.close()
    return answers


def main() -> int:
    heldout = "--heldout" in sys.argv
    questions = load_questions(Path(__file__).with_name("heldout_questions.json")) if heldout else load_questions()
    answers = ask_all(questions)
    results = score(questions, answers)
    print(markdown(results, "First-pass accuracy" if "--first-pass" in sys.argv else "Accuracy (not first-pass: the system was changed after an earlier run on these questions)"))
    for r in results:
        if not r["passed"]:
            print(f"\nFAIL {r['id']} [{r['category']}] {r['question']}\n     {r['answer'][:300]}")
    if "--save" in sys.argv:
        name = sys.argv[sys.argv.index("--save") + 1]
        (Path(__file__).parent / "results" / f"{name}.json").write_text(
            json.dumps({"system": "dashboard chat (built-in tools, no language model)", "summary": summary(results), "results": results}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
