"""Ask every evaluation question to the live backend (OpenAI model + MySQL) and score the answers.

    docker compose up -d        # the app must be running, seeded, with BUSINESS_NOW=2026-04-01T08:00:00+08:00 and your API key
    python -m evaluation.run_backend --first-pass --save backend_first_run     # --first-pass labels the figure; use it only for the very first run

A rate limit (HTTP 429), a provider outage (502) or a timeout (504) means the model never answered: that turn is retried with
backoff and the count is reported, not graded. Every other answer, including an error the system itself returns, is graded as is.
Before anything is graded, one "Hello" checks the server is up and on the evaluation date, so a mistake cannot use up the first pass.

Uses the chat endpoint, one fresh session per question (multi-turn questions share one session). It spends OpenAI credit
(about one model call per question). Run it ONCE and report that number: re-running after fixes is a different number.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .score import load_questions, markdown, score, summary

URL = "http://127.0.0.1:8000/api/v1/workflow/chat"
BUSINESS_DATE = "2026-04-01"          # every evaluation question is asked on this date
TRANSPORT = {429, 502, 504}           # the model was never reached (rate limit, provider down, timeout): retry, do not grade
RETRIES, PAUSE = 4, 2.0               # seconds between turns; backoff doubles from 10 s on a transport failure


def post(url: str, message: str, session_id: str | None) -> dict:
    body = json.dumps({"message": message, **({"session_id": session_id} if session_id else {})}).encode()
    headers = {"Content-Type": "application/json"}
    if os.getenv("THREADPILOT_TOKEN"):     # only needed when the server sets API_ACCESS_TOKEN
        headers["X-ThreadPilot-Token"] = os.environ["THREADPILOT_TOKEN"]
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read())


def turn(url: str, message: str, session: str | None, log: dict, send=post, sleep=time.sleep) -> dict:
    """One turn. A transport failure (the model never answered) is retried with backoff and counted in `log`;
    any other HTTP error is the system's real answer and is graded as it is."""
    for attempt in range(RETRIES + 1):
        try:
            return send(url, message, session)
        except urllib.error.HTTPError as e:
            if e.code not in TRANSPORT or attempt == RETRIES:
                return {"answer": f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}", "http_error": e.code}
            log["transport_retries"] = log.get("transport_retries", 0) + 1
            sleep(10 * 2 ** attempt)
    raise AssertionError("unreachable")


def ask_all(questions: list[dict], url: str = URL, send=post, sleep=time.sleep) -> tuple[dict[str, str], dict]:
    answers, log = {}, {"transport_retries": 0}
    for q in questions:
        session = None
        for text in q["turns"]:
            reply = turn(url, text, session, log, send, sleep)
            session = (reply.get("state") or {}).get("session_id", session)
            sleep(PAUSE)
        answers[q["id"]] = reply.get("answer", "")
    return answers, log


def preflight(url: str = URL, send=post) -> str | None:
    """Spend one model call before the real run: refuse to start if the server is not answering on the evaluation date.
    A first pass can only be run once, so a wrong BUSINESS_NOW or a missing key must not use it up."""
    try:
        reply = send(url, "Hello", None)
    except urllib.error.HTTPError as e:
        return f"server answered HTTP {e.code}: {e.read().decode(errors='replace')[:200]}"
    except OSError as e:
        return f"cannot reach {url}: {e}"
    if reply.get("business_date") != BUSINESS_DATE:
        return f"server business date is {reply.get('business_date')}, not {BUSINESS_DATE}: set BUSINESS_NOW={BUSINESS_DATE}T08:00:00+08:00"
    return None


def main() -> int:
    problem = preflight()
    if problem:
        print("Not started, nothing graded:", problem)
        return 2
    questions = load_questions()
    answers, log = ask_all(questions)
    results = score(questions, answers)
    print(markdown(results, "First-pass accuracy" if "--first-pass" in sys.argv else "Accuracy (not first-pass)"))
    print(f"\nTransport retries (rate limit / provider down / timeout, model never answered): {log['transport_retries']}")
    for r in results:
        if not r["passed"]:
            print(f"\nFAIL {r['id']} [{r['category']}] {r['question']}\n     {r['answer'][:300]}")
    if "--save" in sys.argv:
        name = sys.argv[sys.argv.index("--save") + 1]
        (Path(__file__).parent / "results" / f"{name}.json").write_text(
            json.dumps({"system": "backend (OpenAI model + MySQL)", "first_pass": "--first-pass" in sys.argv,
                        "transport_retries": log["transport_retries"], "summary": summary(results), "results": results}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
