"""The team's own screens (frontend/) must follow the data, not text frozen to the first snapshot, and must use the one
definition of normal. A tiny local web server serves frontend/ and the browser's /api/snapshot call is answered from the
team's test fixture, so no backend or database is needed."""
import copy
import functools
import http.server
import json
import threading

import pytest

from dashboard_helpers import ROOT

FIXTURE = json.loads((ROOT / "tests" / "e2e" / "snapshot.fixture.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def base_url():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "frontend"))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def browser_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"headless browser not available: {e}")
        yield browser
        browser.close()


def open_route(browser, base_url, route, snapshot):
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/api/snapshot", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(snapshot)))
    page.goto(f"{base_url}/#/{route}")
    page.wait_for_selector("#app .page, #app .card", timeout=8000)
    page.wait_for_timeout(400)
    return page, errors


def test_dashboard_heading_follows_the_business_date(browser_page, base_url):
    snap = copy.deepcopy(FIXTURE)
    snap["today"] = "2026-04-09"
    page, errors = open_route(browser_page, base_url, "dashboard", snap)
    text = page.inner_text("#app")
    assert "2026-04-09" in text and "Wednesday, April 1" not in text   # the team dashboard shows the business date, not a frozen one
    assert "Business date · 2026-04-09" in page.text_content("body")
    assert errors == []
    page.close()


def test_order_count_is_not_frozen_at_120(browser_page, base_url):
    snap = copy.deepcopy(FIXTURE)
    snap["orders"] = snap["orders"][:-3]
    page, errors = open_route(browser_page, base_url, "dashboard", snap)
    assert f"of {len(snap['orders'])} total orders" in page.inner_text("#app") and "of 120 total orders" not in page.inner_text("#app")
    assert errors == []
    page.close()


def test_dashboard_uses_the_one_definition_of_normal(browser_page, base_url):
    page, errors = open_route(browser_page, base_url, "dashboard", FIXTURE)
    text = page.inner_text("#app")
    assert "same weekdays" in text and "normal band" in text
    assert "20 working" not in text and "prior 20" not in text
    assert errors == []
    page.close()


def test_data_page_describes_the_loaded_data(browser_page, base_url):
    snap = copy.deepcopy(FIXTURE)
    snap["orders"] = snap["orders"][:-2]
    page, errors = open_route(browser_page, base_url, "settings", snap)
    text = page.inner_text("#app")
    assert f"orders.csv · {len(snap['orders'])} rows" in text and "orders.csv · 120 rows" not in text
    assert f"production_log.csv · {len(snap['production_log'])} rows" in text
    assert "Production coverage: Jan 01–Mar 31, 2026" in text          # derived from the production rows now, not typed in
    assert errors == []
    page.close()


def test_sidebar_has_a_morning_briefing_link_to_the_static_page(browser_page, base_url):
    page, errors = open_route(browser_page, base_url, "dashboard", FIXTURE)
    link = page.locator('aside.sidebar nav a', has_text="Morning Briefing")
    assert link.count() == 1 and link.get_attribute("href") == "briefing/index.html"
    assert page.locator('aside.sidebar nav a[aria-current="page"]').count() == 1      # exactly one current page, and it is not the link
    assert errors == []
    page.close()
