"""The morning email's "Send with Outlook" button, end to end in a real browser.

Microsoft is replaced at its two edges only: the sign-in library (a stand-in for vendor/msal-browser.min.js with the same
calls) and Microsoft Graph's sendMail (answered by the test, which keeps what would have been sent). ThreadPilot's
email API is a small in-memory copy of backend/app/api/dashboard_api.py; the backend's own tests cover the real one.

What is checked: the sign-in window is opened by the click itself, before anything is awaited on the network (otherwise
browsers block it); exactly the reviewed text goes to the people in To and Cc; a send is recorded only after Outlook
accepts it; the second morning is one click with no sign-in; failures say plainly that nothing was sent.
"""
import functools
import http.server
import json
import re
import threading

import pytest
from conftest import ROOT

CLIENT_ID = "00000000-1111-2222-3333-444444444444"
DAY = "2026-10-12"

FAKE_MSAL = """
window.__events = window.__events || [];
window.__msal = {mode: {silent: 'ok', popup: 'ok'}, account: null, active: null, config: null, popups: 0};
class InteractionRequiredAuthError extends Error {}
window.msal = {InteractionRequiredAuthError, PublicClientApplication: class {
  constructor(config) { __msal.config = config; }
  async initialize() {}
  getActiveAccount() { return __msal.active; }
  getAllAccounts() { return __msal.account ? [__msal.account] : []; }
  setActiveAccount(a) { __msal.active = a; if (a) __msal.account = a; }
  async acquireTokenSilent(r) {
    __events.push('silent');
    if (__msal.mode.silent !== 'ok') { const e = new InteractionRequiredAuthError('x'); e.errorCode = 'interaction_required'; throw e; }
    return {accessToken: 'silent-token', account: r.account};
  }
  async acquireTokenPopup(r) {
    __events.push('popup:' + r.scopes.join(','));
    __msal.popups += 1;
    if (__msal.pending && r.overrideInteractionInProgress) {
      const e = new Error('cancelled'); e.errorCode = 'interaction_in_progress_cancelled'; __msal.pending(e); __msal.pending = null;
    }
    if (__msal.mode.popup === 'hang') return new Promise((_, reject) => { __msal.pending = reject; });
    if (__msal.mode.popup !== 'ok') { const e = new Error('no'); e.errorCode = __msal.mode.popup; throw e; }
    return {accessToken: 'popup-token', account: {username: 'gm@factory.com'}};
  }
  async clearCache() { __events.push('clear'); __msal.account = null; __msal.active = null; }
}};
"""

# Log every request the page makes, in order, next to the fake sign-in's own log.
LOG_FETCH = """
window.__events = window.__events || [];
const realFetch = window.fetch;
window.fetch = (input, init = {}) => { window.__events.push((init.method || 'GET') + ' ' + String(input)); return realFetch(input, init); };
"""


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


@pytest.fixture(scope="module")
def frontend():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "frontend"))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


class Backend:
    """In-memory stand-in for the email API, plus Microsoft Graph."""

    def __init__(self):
        self.draft = {"briefing_day": DAY, "subject": f"ThreadPilot morning summary | {DAY}",
                      "body": "Hello team,\n\nMorning summary — test body", "version": 1,
                      "created_at": "2026-10-12T07:00:00+08:00", "updated_at": "2026-10-12T07:00:00+08:00",
                      "to": [], "cc": [], "sent": None}
        self.saves, self.records, self.graph = [], [], []
        self.graph_status = 202

    def api(self, route):
        req, url = route.request, route.request.url
        snapshot = (ROOT / "tests/e2e/snapshot.fixture.json").read_text(encoding="utf-8")
        dashboard = (ROOT / "tests/e2e/dashboard.fixture.json").read_text(encoding="utf-8")
        if url.endswith("/api/snapshot"):
            return route.fulfill(status=200, content_type="application/json", body=snapshot)
        if url.endswith("/api/dashboard"):
            return route.fulfill(status=200, content_type="application/json", body=dashboard)
        if re.search(r"/api/dashboard/briefings/[\d-]+/email/sent$", url):
            body = req.post_data_json
            self.records.append(body)
            self.draft["sent"] = {"at": "2026-10-12T07:45:00+08:00", "by": body["sent_by"], "version": body["version"],
                                  "count": len(self.records)}
            self.draft.update(to=body["to"], cc=body.get("cc", []))
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(self.draft))
        if re.search(r"/api/dashboard/briefings/[\d-]+/email$", url):
            if req.method == "PUT":
                body = req.post_data_json
                self.saves.append(body)
                self.draft.update(subject=body["subject"], body=body["body"], version=self.draft["version"] + 1)
                if body.get("to") is not None:
                    self.draft["to"] = body["to"]
                if body.get("cc") is not None:
                    self.draft["cc"] = body["cc"]
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(self.draft))
        return route.fulfill(status=404, content_type="application/json", body="{}")

    def send_mail(self, route):
        self.graph.append({"auth": route.request.headers.get("authorization"), "body": route.request.post_data_json})
        if self.graph_status == 202:
            return route.fulfill(status=202, body="")
        return route.fulfill(status=self.graph_status, content_type="application/json",
                             body=json.dumps({"error": {"code": "ErrorAccessDenied", "message": "Access is denied."}}))


def open_page(browser, frontend, backend, client_id=CLIENT_ID, width=1280, web="office", phone=False, init=""):
    page = browser.new_page(viewport={"width": width, "height": 900}, has_touch=phone, is_mobile=phone)
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())       # "already sent, send again?"
    page.add_init_script(LOG_FETCH + init)
    config = (ROOT / "frontend/config.js").read_text(encoding="utf-8").replace("clientId: ''", f"clientId: '{client_id}'")
    config = config.replace("web: 'office'", f"web: '{web}'")
    # Outlook on the web, for the window opened without an app registration (popups need the context's routes).
    page.context.route("https://outlook.*.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body="<p>Outlook (stand-in)</p>"))
    page.route("**/config.js", lambda r: r.fulfill(status=200, content_type="text/javascript", body=config))
    page.route("**/vendor/msal-browser.min.js", lambda r: r.fulfill(status=200, content_type="text/javascript", body=FAKE_MSAL))
    page.route("**/api/**", backend.api)
    page.route("https://graph.microsoft.com/**", backend.send_mail)
    page.goto(f"{frontend}/#/dashboard")
    page.locator('[data-action="briefing-email"]').click()
    page.locator("#briefing-email-dialog").wait_for()
    return page


def status(page):
    page.wait_for_function("() => !document.querySelector('.email-send').disabled")
    return page.locator(".email-status").inner_text()


def reopen(page):
    page.locator(".email-close").click()
    page.locator('[data-action="briefing-email"]').click()
    page.locator("#briefing-email-dialog").wait_for()


def test_first_send_signs_in_from_the_click_then_sends_exactly_the_reviewed_email(browser, frontend):
    backend = Backend()
    page = open_page(browser, frontend, backend)
    dialog = page.locator("#briefing-email-dialog")
    assert dialog.locator(".email-send").inner_text() == "Send with Outlook"
    page.wait_for_function("() => /first time/i.test(document.querySelector('.email-account').textContent)")

    dialog.locator(".email-send").click()
    assert status(page) == "Add at least one address in To."
    dialog.locator("[name=to]").fill("planner@factory.com, ops@")
    dialog.locator(".email-send").click()
    assert status(page) == "Check these addresses: ops@"
    assert backend.graph == [] and backend.saves == []

    dialog.locator("[name=to]").fill("planner@factory.com; ops@factory.com  planner@FACTORY.com")
    dialog.locator("[name=cc]").fill("boss@factory.com")
    dialog.locator("[name=body]").fill("Edited by the GM before sending.\nLine two <b>not html</b>")
    dialog.locator(".email-send").click()
    assert status(page).startswith("Sent ")

    events = page.evaluate("window.__events")
    order = [next(i for i, e in enumerate(events) if e.startswith(p)) for p in
             ("popup:Mail.Send", "PUT ", "POST https://graph.microsoft.com/v1.0/me/sendMail", "POST " + "http")]
    assert order[0] < order[1] < order[2], events          # sign-in first, then save, then send
    assert any(e.endswith("/email/sent") for e in events[order[2]:]), events   # recorded only after Outlook accepted it

    assert backend.saves[-1]["to"] == ["planner@factory.com", "ops@factory.com"]   # duplicates (any case) dropped
    assert backend.saves[-1]["cc"] == ["boss@factory.com"]
    sent = backend.graph[-1]
    assert sent["auth"] == "Bearer popup-token"
    message = sent["body"]["message"]
    assert message["subject"] == f"ThreadPilot morning summary | {DAY}"
    assert message["body"] == {"contentType": "Text", "content": "Edited by the GM before sending.\nLine two <b>not html</b>"}
    assert [r["emailAddress"]["address"] for r in message["toRecipients"]] == ["planner@factory.com", "ops@factory.com"]
    assert [r["emailAddress"]["address"] for r in message["ccRecipients"]] == ["boss@factory.com"]
    assert sent["body"]["saveToSentItems"] is True
    assert backend.records == [{"version": 2, "to": ["planner@factory.com", "ops@factory.com"], "cc": ["boss@factory.com"],
                                "sent_by": "gm@factory.com"}]
    config = page.evaluate("__msal.config")
    assert config["auth"]["clientId"] == CLIENT_ID and config["auth"]["redirectUri"].endswith("/auth-redirect.html")
    assert config["cache"]["cacheLocation"] == "localStorage"

    # The next send is one click: no sign-in window, the saved sign-in is used.
    reopen(page)
    assert dialog.locator(".email-send").inner_text() == "Send again"
    assert dialog.locator(".email-status").inner_text().startswith("Sent ")
    page.wait_for_function("() => document.querySelector('.email-account').textContent.includes('gm@factory.com')")
    dialog.locator(".email-send").click()
    assert status(page).startswith("Sent ")
    assert page.evaluate("__msal.popups") == 1 and backend.graph[-1]["auth"] == "Bearer silent-token"
    assert len(backend.records) == 2
    assert page.errors == []


def test_failures_say_nothing_was_sent_and_a_lost_sign_in_window_can_be_retried(browser, frontend):
    backend = Backend()
    backend.draft["to"] = ["gm@factory.com"]
    page = open_page(browser, frontend, backend)
    dialog = page.locator("#briefing-email-dialog")

    page.evaluate("__msal.mode.popup = 'popup_window_error'")
    dialog.locator(".email-send").click()
    assert "blocked the Microsoft sign-in window" in status(page) and "Nothing was sent" in status(page)

    page.evaluate("__msal.mode.popup = 'user_cancelled'")
    dialog.locator(".email-send").click()
    assert status(page) == "Microsoft sign-in was closed. Nothing was sent."

    page.evaluate("__msal.mode.popup = 'ok'")
    backend.graph_status = 403
    dialog.locator(".email-send").click()
    assert "not allowed to send email" in status(page) and "Nothing was sent" in status(page)

    backend.graph_status = 503
    dialog.locator(".email-send").click()
    assert "Check Sent Items" in status(page)          # a server error might still have sent it: say so, never "not sent"

    assert backend.records == [] and backend.draft["sent"] is None
    assert len(backend.graph) == 2

    # The manager closes Microsoft's window without signing in (the library cannot tell): Send stays pressable,
    # says what to do, and pressing it again starts a fresh sign-in that goes through.
    page.evaluate("__msal.account = null; __msal.active = null; __msal.mode.popup = 'hang'")
    backend.graph_status = 202
    dialog.locator(".email-send").click()
    page.wait_for_function("() => /Press Send again/.test(document.querySelector('.email-status').textContent)")
    assert dialog.locator(".email-send").is_enabled() and dialog.locator("[name=body]").is_disabled()
    page.evaluate("__msal.mode.popup = 'ok'")
    dialog.locator(".email-send").click()
    assert status(page).startswith("Sent ")
    assert len(backend.graph) == 3 and len(backend.records) == 1

    # "Use another account" forgets the sign-in on this device.
    page.wait_for_function("() => !!document.querySelector('.email-forget')")
    dialog.locator(".email-forget").click()
    page.wait_for_function("() => /Signed out/.test(document.querySelector('.email-account').textContent)")
    assert page.evaluate("__msal.account") is None
    assert page.errors == []


def compose_fields(url):
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(url)
    return parsed.netloc + parsed.path, {k: v[0] for k, v in parse_qs(parsed.query).items()}


@pytest.mark.parametrize("web, address", [("office", "outlook.office.com/mail/deeplink/compose"),
                                          ("live", "outlook.live.com/mail/0/deeplink/compose")])
def test_without_an_app_registration_it_opens_an_outlook_window_filled_in(browser, frontend, web, address):
    backend = Backend()
    backend.draft["to"] = ["gm@factory.com"]
    page = open_page(browser, frontend, backend, client_id="", web=web)
    dialog = page.locator("#briefing-email-dialog")
    assert dialog.locator(".email-send").inner_text() == "Open in Outlook"
    assert "new Outlook window" in dialog.locator(".email-account").inner_text()
    dialog.locator("[name=cc]").fill("boss@factory.com")
    dialog.locator("[name=body]").fill("Checked by the GM.\nSecond line & more")
    with page.expect_popup() as opened:
        dialog.locator(".email-send").click()
    popup = opened.value
    popup.wait_for_url("https://outlook.*.com/**")
    where, fields = compose_fields(popup.url)
    assert where == address
    assert fields == {"to": "gm@factory.com", "cc": "boss@factory.com", "subject": f"ThreadPilot morning summary | {DAY}",
                      "body": "Checked by the GM.\r\nSecond line & more"}
    assert popup.evaluate("window.opener") is None              # Outlook's page gets no handle back to ThreadPilot
    assert status(page) == "Opened in Outlook in a new window. Check it and press Send there."
    assert backend.saves[-1]["cc"] == ["boss@factory.com"]      # saved before opening, so the draft matches
    assert backend.records == []                                 # ThreadPilot cannot see the send, so it does not claim one
    assert not page.evaluate("'msal' in window")                 # the Microsoft library is never loaded without a registration
    assert page.errors == []


def test_a_blocked_outlook_window_leaves_a_link_to_open_it(browser, frontend):
    backend = Backend()
    backend.draft["to"] = ["gm@factory.com"]
    page = open_page(browser, frontend, backend, client_id="", init="window.open = () => null;")
    page.locator(".email-send").click()
    assert status(page).startswith("The browser blocked the Outlook window.")
    link = page.locator(".email-status a")
    assert link.inner_text() == "Open Outlook" and link.get_attribute("target") == "_blank"
    assert compose_fields(link.get_attribute("href"))[1]["to"] == "gm@factory.com"
    assert page.errors == []


def test_on_a_phone_it_opens_the_outlook_app_instead(browser, frontend):
    backend = Backend()
    backend.draft["to"] = ["gm@factory.com"]
    page = open_page(browser, frontend, backend, client_id="", width=390, phone=True,
                     init="window.__opened = []; window.open = (...a) => { window.__opened.push(a); return null; };")
    assert "Outlook app" in page.locator(".email-account").inner_text()
    page.locator(".email-send").click()
    assert status(page) == "Opened in your mail app. Check it and press Send there."
    assert page.evaluate("window.__opened") == []               # no browser window on a phone
    link = page.evaluate("ThreadPilotOutlook.mailto({to:['a@x.com','b@x.com'],cc:['c@x.com'],subject:'Morning | 12 Oct',body:'Line 1\\nLine 2 & more'})")
    assert link == "mailto:a%40x.com,b%40x.com?cc=c%40x.com&subject=Morning%20%7C%2012%20Oct&body=Line%201%0D%0ALine%202%20%26%20more"


@pytest.mark.parametrize("width", [320, 360, 390])
def test_the_email_dialog_fits_a_phone(browser, frontend, width):
    backend = Backend()
    backend.draft.update(to=["planner@factory.com", "ops@factory.com"], cc=["a.very.long.address.for.testing@factory-example.com"])
    page = open_page(browser, frontend, backend, width=width)
    page.wait_for_function("() => /first time/i.test(document.querySelector('.email-account').textContent)")
    overflow = page.evaluate("""() => { const d = document.querySelector('#briefing-email-dialog');
        return [document.documentElement.scrollWidth - document.documentElement.clientWidth, d.scrollWidth - d.clientWidth]; }""")
    assert overflow == [0, 0]
    box = page.locator(".email-send").bounding_box()
    assert box["height"] >= 40                         # big enough to tap
    assert box["y"] + box["height"] <= page.viewport_size["height"]   # Send is on screen without scrolling
    clipped = page.evaluate("""() => [...document.querySelectorAll('.email-footer button')]
        .filter(b => b.scrollWidth > b.clientWidth || b.getClientRects().length > 1).map(b => b.textContent)""")
    assert clipped == []


def test_the_sign_in_return_page_loads_on_its_own(browser, frontend):
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{frontend}/auth-redirect.html")       # opened without a sign-in result: says so instead of failing
    page.wait_for_function("() => /You can close this window/.test(document.body.textContent)")
    assert errors == []
