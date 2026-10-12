"""The live-backend runner: a rate limit is retried and counted, never graded; a real error is graded; a wrong date stops the run."""
import io
import urllib.error

from evaluation import run_backend


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(b'{"detail": "x"}'))


def test_a_rate_limit_is_retried_and_counted_not_graded():
    calls = []

    def send(url, message, session):
        calls.append(message)
        if len(calls) == 1:
            raise http_error(429)
        return {"answer": "34 orders are in progress.", "state": {"session_id": "s1"}}

    answers, log = run_backend.ask_all([{"id": "Q01", "turns": ["How many orders are in progress?"]}], send=send, sleep=lambda s: None)
    assert answers == {"Q01": "34 orders are in progress."} and log["transport_retries"] == 1 and len(calls) == 2


def test_a_real_error_from_the_system_is_graded_as_it_is():
    def send(url, message, session):
        raise http_error(422)

    answers, log = run_backend.ask_all([{"id": "Q99", "turns": ["?"]}], send=send, sleep=lambda s: None)
    assert answers["Q99"].startswith("HTTP 422") and log["transport_retries"] == 0


def test_multi_turn_questions_share_one_session():
    seen = []

    def send(url, message, session):
        seen.append(session)
        return {"answer": "ok", "state": {"session_id": "s7"}}

    run_backend.ask_all([{"id": "Q11", "turns": ["How is ORD-005 doing?", "When is it due?"]}], send=send, sleep=lambda s: None)
    assert seen == [None, "s7"]


def test_the_wrong_business_date_stops_the_run_before_anything_is_graded():
    assert "BUSINESS_NOW" in run_backend.preflight(send=lambda u, m, s: {"answer": "hi", "business_date": "2026-10-11"})
    assert run_backend.preflight(send=lambda u, m, s: {"answer": "hi", "business_date": "2026-04-01"}) is None
