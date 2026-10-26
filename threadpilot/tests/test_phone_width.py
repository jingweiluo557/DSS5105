"""No sideways scrolling on a phone, for the morning briefing and the team's nine screens.

Measured against the page's real width (documentElement.clientWidth). Comparing with window.innerWidth, as the older e2e
scripts did, passes even when the page overflows: a mobile browser widens innerWidth to fit whatever overflows.

Found this way: hidden "Actions" labels for screen readers (.sr-only) inside the wide order tables escaped their scroll box,
so the whole page scrolled sideways on phones (the briefing page was 878 px wide on a 390 px phone).
"""
import functools
import http.server
import threading

import pytest
from conftest import ROOT

WIDTHS = (320, 360, 390)
TEAM_SCREENS = ("cover", "dashboard", "orders", "risk", "feasibility", "ai", "messages", "activity", "settings")
OVERFLOW = "document.documentElement.scrollWidth - document.documentElement.clientWidth"


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001 - browser not installed
            pytest.skip(f"headless browser not available: {e}")
        yield b
        b.close()


def test_the_briefing_page_never_scrolls_sideways(browser, site):
    found = {}
    for w in WIDTHS:
        page = browser.new_page(viewport={"width": w, "height": 800})
        page.goto(site[0].as_uri())
        for day in ("0", "8", "14"):
            page.select_option("#daysel", day)
            page.wait_for_timeout(200)
            found[f"{w}px day {day}"] = page.evaluate(OVERFLOW)
        page.click("#chatFab")
        page.wait_for_timeout(200)
        found[f"{w}px chat open"] = page.evaluate(OVERFLOW)
        page.close()
    assert {k: v for k, v in found.items() if v > 0} == {}


@pytest.fixture(scope="module")
def team_server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "frontend"))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_the_team_screens_never_scroll_sideways(browser, team_server):
    fixture = (ROOT / "tests" / "e2e" / "snapshot.fixture.json").read_text(encoding="utf-8")
    found = {}
    for w in (360, 390):
        page = browser.new_page(viewport={"width": w, "height": 800})
        page.route("**/api/snapshot", lambda r: r.fulfill(status=200, content_type="application/json", body=fixture))
        for route in TEAM_SCREENS:
            page.goto(f"{team_server}/#/{route}")
            page.wait_for_timeout(500)
            found[f"{w}px {route}"] = page.evaluate(OVERFLOW)
        page.close()
    assert {k: v for k, v in found.items() if v > 0} == {}
