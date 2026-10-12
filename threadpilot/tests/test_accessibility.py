"""Automated accessibility check (axe-core, WCAG 2.1 A and AA plus best practice) on the morning dashboard in its main states and on the
team's nine screens. It finds roughly a third of possible accessibility problems, so it is a floor, not a certificate: keyboard use and
screen-reader wording still need a human.

Needs axe-core, which is not a Python package. Install it once and point the test at it, otherwise the test skips itself:

    npm install --prefix /tmp/axe axe-core@4.14.0
    AXE_CORE_PATH=/tmp/axe/node_modules/axe-core/axe.min.js python -m pytest tests/test_accessibility.py
"""
import functools
import http.server
import os
import threading
from pathlib import Path

import pytest

from dashboard_helpers import ROOT

AXE = os.environ.get("AXE_CORE_PATH") or "/tmp/axe/node_modules/axe-core/axe.min.js"
RULES = "{runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}}"
RUN = (f"axe.run(document, {RULES}).then(r => r.violations.map(v => v.id + ' x' + v.nodes.length + ' e.g. ' + "
       "v.nodes[0].target.join(' ').slice(0, 60)))")
pytestmark = pytest.mark.skipif(not Path(AXE).exists(), reason="axe-core not installed (see the module docstring)")

TEAM_SCREENS = ("cover", "dashboard", "orders", "risk", "feasibility", "ai", "messages", "activity", "settings")


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def violations(page):
    page.add_script_tag(path=AXE)
    return page.evaluate(RUN)


def test_morning_dashboard_states(browser, site):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(site[0].as_uri())
    page.evaluate("localStorage.clear()")
    page.reload()
    page.select_option("#daysel", "8")
    page.wait_for_timeout(300)
    found = {"light": violations(page)}
    page.click("#theme")
    found["dark"] = violations(page)
    page.click("#theme")
    page.click("#settingsBtn")
    found["settings dialog"] = violations(page)
    page.click("#stDone")
    page.click('[data-tp-open="memo"]')
    found["memo dialog"] = violations(page)
    page.click("#mmCancel")
    page.click('[data-tp-actions="ORD-120"]')
    page.wait_for_timeout(250)
    found["follow-up panel"] = violations(page)
    page.keyboard.press("Escape")
    page.click("#chatFab")
    page.fill("#chatInput", "Should we expedite ORD-120?")
    page.press("#chatInput", "Enter")
    page.wait_for_timeout(450)
    found["chat"] = violations(page)
    phone = browser.new_page(viewport={"width": 390, "height": 844})
    phone.goto(site[0].as_uri())
    phone.select_option("#daysel", "8")
    phone.wait_for_timeout(300)
    found["phone width"] = violations(phone)
    assert {k: v for k, v in found.items() if v} == {}


@pytest.fixture(scope="module")
def team_server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "frontend"))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_team_screens(browser, team_server):
    fixture = (ROOT / "tests" / "e2e" / "snapshot.fixture.json").read_text(encoding="utf-8")
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.route("**/api/snapshot", lambda r: r.fulfill(status=200, content_type="application/json", body=fixture))
    found = {}
    for route in TEAM_SCREENS:
        page.goto(f"{team_server}/#/{route}")
        page.wait_for_timeout(700)
        found[route] = violations(page)
    assert {k: v for k, v in found.items() if v} == {}
