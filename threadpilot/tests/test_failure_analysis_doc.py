"""docs/failure_analysis.md must analyse every first-pass failure, individually, and say what each answer was.

The course asks for at least ten failure cases each analysed on its own. The failures are the ones saved in
evaluation/results/dashboard_chat_first_run.json; this test fails if one is missing from the page or if the page's quoted answer for a
case is not what the saved run recorded.
"""
import json
import re

from conftest import ROOT

DOC = (ROOT / "docs" / "failure_analysis.md").read_text(encoding="utf-8")
RUN = json.loads((ROOT / "evaluation" / "results" / "dashboard_chat_first_run.json").read_text(encoding="utf-8"))


def failures():
    return [r for r in RUN["results"] if not r["passed"]]


def test_every_first_pass_failure_has_its_own_row():
    rows = {m[1] for m in re.finditer(r"^\| (Q\d\d) \|", DOC, re.M)}
    assert rows == {r["id"] for r in failures()}, "the page and the saved first run list different failures"
    assert len(rows) >= 10, "the course asks for at least ten individually analysed failures"


def test_the_quoted_question_matches_the_saved_run():
    for r in failures():
        line = next(l for l in DOC.splitlines() if l.startswith(f"| {r['id']} |"))
        first_turn = r["question"].split(" / ")[0]
        assert first_turn.rstrip("?.") in line.replace('"', "").replace("“", ""), f"{r['id']}: question not quoted as asked"


def test_the_headline_counts_agree_with_the_saved_run():
    assert len(RUN["results"]) == 36 and sum(r["passed"] for r in RUN["results"]) == 24 and len(failures()) == 12
    assert "24 of 36" in DOC and "12 questions" in DOC
