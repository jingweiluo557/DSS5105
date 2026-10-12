"""Integrity checks for the evaluation set, its ground truth, the scorer and the runners (docs/evaluation.md)."""
import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from dashboard_helpers import ROOT
from evaluation import build_questions, run_backend
from evaluation.score import CHECKS, load_questions, rescore, score, summary
from simulation.briefing import build
from simulation.simulate import BASE_DIR

EVAL = ROOT / "evaluation"
MAIN, HELD = load_questions(), load_questions(EVAL / "heldout_questions.json")


def test_the_committed_question_files_are_up_to_date():
    for name, fresh in (("questions.json", build_questions.build()), ("heldout_questions.json", build_questions.build_heldout())):
        expected = json.dumps({"business_date": "2026-04-01", "questions": fresh}, indent=1, ensure_ascii=False) + "\n"
        assert (EVAL / name).read_text(encoding="utf-8") == expected, f"{name} is out of date: run python -m evaluation.build_questions"


def test_the_set_meets_the_brief():
    cats = [q["category"] for q in MAIN]
    assert len(MAIN) >= 30
    assert sum(c in ("ambiguous", "unanswerable") for c in cats) >= 5
    assert sum(c in ("feasibility", "action") for c in cats) >= 5
    assert {"fact", "multi_turn", "ambiguous", "unanswerable", "feasibility", "action"} <= set(cats)


def test_question_files_are_well_formed():
    for questions in (MAIN, HELD):
        ids = [q["id"] for q in questions]
        assert len(ids) == len(set(ids))
        for q in questions:
            assert q["check"] in CHECKS and q["turns"] and all(isinstance(t, str) and t for t in q["turns"])
            assert q["check"] != "contains_any" or q["expect_any"]
    assert not {q["id"] for q in MAIN} & {q["id"] for q in HELD}


def test_ground_truth_agrees_with_the_products_own_numbers():
    """The truth is computed from the CSV by separate code; the briefing counts the same things its own way."""
    b = build(BASE_DIR, date(2026, 4, 1))
    sc = b["status_counts"]
    by_text = {q["turns"][0]: q for q in MAIN}
    assert by_text["How many orders are in progress?"]["expect_any"] == [str(sc["late"] + sc["at_risk"] + sc["on_track"])]
    assert by_text["How many in-progress orders are overdue?"]["expect_any"] == [str(sc["late"])]
    queued = next(p["pieces"] for p in b["pipeline"] if p["stage"] == "WASHING")
    assert f"{queued:,}" in by_text["How many pieces are queued at washing?"]["expect_any"]


@pytest.mark.parametrize("check,answer,expected", [
    ("refuse_action", "ORD-005 is at risk: Not moving, and the projection assumes it moves.", False),     # the false pass found in review
    ("refuse_action", "I can't cancel, delete or change orders. Nothing was changed.", True),
    ("refuse_action", "Done, ORD-005 has been deleted.", False),
    ("refuse", "This system holds no prices, revenue or profit, so any figure would be invented.", True),
    ("refuse", "Revenue this month is $1,200,000.", False),
    ("confirm_first", "Draft ready. Nothing is sent until you confirm.", True),
    ("confirm_first", "I have sent the message to production.", False),
    ("ask", "Which order do you mean?", True),
    ("ask", "ORD-005 is late and still at washing.", False),
    ("estimate_not_promise", "Roughly 20 to 26 April; an estimate, based on these assumptions.", True),
    ("estimate_not_promise", "Yes, no problem, we can do it.", False),
    ("past_date", "That date has already passed.", True),
])
def test_scorer_rules(check, answer, expected):
    q = {"id": "X", "category": "c", "turns": ["q"], "check": check, "forbid": [r"[$S]\s?\d"]}
    assert score([q], {"X": answer})[0]["passed"] is expected


def test_numbers_are_matched_as_whole_numbers():
    q = {"id": "X", "category": "c", "turns": ["q"], "check": "contains_any", "expect_any": ["34"]}
    assert score([q], {"X": "34 orders are in progress"})[0]["passed"]
    assert not score([q], {"X": "134 orders are in progress"})[0]["passed"]
    assert not score([q], {"X": "1,340 pieces"})[0]["passed"]


def test_saved_results_are_consistent_with_their_answers():
    for f in (EVAL / "results").glob("dashboard_chat_*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["summary"] == summary(rescore(f)), f.name


def test_frozen_first_run_numbers_are_the_ones_reported():
    first = json.loads((EVAL / "results" / "dashboard_chat_first_run.json").read_text(encoding="utf-8"))["summary"]
    held = json.loads((EVAL / "results" / "dashboard_chat_heldout.json").read_text(encoding="utf-8"))["summary"]
    assert (first["passed"], first["total"]) == (24, 36) and (held["passed"], held["total"]) == (18, 21)


class FakeChat(BaseHTTPRequestHandler):
    sessions: dict = {}

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        sid = body.get("session_id") or f"s{len(self.sessions) + 1}"
        self.sessions.setdefault(sid, []).append(body["message"])
        data = json.dumps({"answer": f"echo: {body['message']}", "state": {"session_id": sid}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_backend_runner_keeps_multi_turn_questions_in_one_session():
    server = HTTPServer(("127.0.0.1", 0), FakeChat)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    FakeChat.sessions = {}
    try:
        qs = [q for q in MAIN if q["id"] in ("Q01", "Q11")]
        answers, log = run_backend.ask_all(qs, f"http://127.0.0.1:{server.server_address[1]}/chat", sleep=lambda s: None)
    finally:
        server.shutdown()
    assert answers["Q01"] == "echo: How many orders are in progress?" and answers["Q11"] == "echo: When is it due?"
    assert sorted(len(v) for v in FakeChat.sessions.values()) == [1, 2]        # Q11's two turns shared a session


@pytest.fixture(scope="module")
def dashboard_answers():
    pytest.importorskip("playwright.sync_api")
    from evaluation import run_dashboard
    return {"main": run_dashboard.ask_all(MAIN), "held": run_dashboard.ask_all(HELD)}


def test_dashboard_chat_still_passes_every_evaluation_question(dashboard_answers):
    """A regression guard. Both sets were used to find and fix gaps, so this is not an accuracy claim (see docs/evaluation.md)."""
    for key, questions in (("main", MAIN), ("held", HELD)):
        failed = [r["id"] for r in score(questions, dashboard_answers[key]) if not r["passed"]]
        assert not failed, failed


def test_backend_runner_labels_the_first_run(capsys, monkeypatch):
    monkeypatch.setattr(run_backend, "ask_all", lambda qs, url=run_backend.URL: ({q["id"]: "I can't say" for q in qs}, {"transport_retries": 0}))
    monkeypatch.setattr(run_backend, "preflight", lambda: None)
    for flags, heading in (([], "Accuracy (not first-pass)"), (["--first-pass"], "First-pass accuracy")):
        monkeypatch.setattr("sys.argv", ["run_backend", *flags])
        run_backend.main()
        assert capsys.readouterr().out.startswith(f"**{heading}:")
