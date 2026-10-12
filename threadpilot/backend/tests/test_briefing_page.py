"""The morning-briefing page is a plain file inside the web app (frontend/briefing/index.html).

Because it lives in frontend/, the local backend serves it with the rest of the app AND the static Tencent CloudBase
site (which publishes only frontend/) serves it too. No special backend route is needed."""
from pathlib import Path

from .test_api import client  # noqa: F401  (pytest fixture)

THREADPILOT = Path(__file__).resolve().parents[2]


def test_the_briefing_page_is_served_with_the_app(client):
    for url in ('/briefing/index.html', '/briefing/'):
        r = client.get(url)
        assert r.status_code == 200 and 'ThreadPilot' in r.text and 'id="liveLink"' in r.text, url


def test_the_served_page_is_the_committed_demo(client):
    """frontend/briefing/index.html is written by `python -m simulation.render_demo`; a stale copy would show old numbers."""
    served = client.get('/briefing/index.html').content
    assert served == (THREADPILOT / 'demo' / 'briefing_demo.html').read_bytes()


def test_the_briefing_page_links_back_to_the_live_app(client):
    assert 'id="liveLink" href="/#/dashboard"' in client.get('/briefing/index.html').text


def test_the_sidebar_links_to_the_briefing_and_the_cover_still_opens_the_teams_dashboard(client):
    app_js = client.get('/app.js').text
    assert "['briefing/index.html','☀','Morning Briefing']" in app_js          # a sidebar entry for the briefing
    assert "r.includes('/')?r:'#/'+r" in app_js                                # ...linked as a page, not as a #/ route
    assert "link('dashboard','Enter today’s dashboard ↗','','button primary')" in app_js   # the team's own Dashboard is untouched
    assert "['briefing/index.html','☀','Morning Briefing']" in client.get('/workspace.js').text   # the team's final sidebar keeps it too


def test_nothing_outside_the_frontend_folder_is_exposed(client):
    for url in ('/briefing/../backend/.env', '/briefing/../../data/orders.csv', '/briefing/missing.html', '/demo/briefing_demo.html'):
        assert client.get(url).status_code == 404, url
