"""Capture the screenshots used on the Sprint 1 slides from the real demo page, typing the questions into the real chat box.

    pip install -r requirements-dev.txt && python -m playwright install chromium
    python scripts/capture_screenshots.py                 # writes docs/presentation/screens/*.png

Nothing is mocked: the page is demo/briefing_demo.html on "Thursday 9 April 2026 (simulated day 8)", the questions go through the
same input box a user would use, and the pictures are of what the page drew. Run it again after changing the interface.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / "briefing_demo.html"
OUT = ROOT / "docs" / "presentation" / "screens"
DAY = 8                       # Thursday 9 April 2026
TALL = 1180                   # tall enough that a whole short conversation is on screen


class Shots:
    def __init__(self, page, out: Path):
        self.page, self.out, self.names = page, out, []

    def ask(self, question: str) -> None:
        self.page.fill("#chatInput", question)
        self.page.press("#chatInput", "Enter")
        self.page.wait_for_selector("#chatTyping", state="detached")
        self.page.wait_for_timeout(250)

    def click_chip(self, label: str) -> None:
        self.page.locator("#chatLog .chip", has_text=label).last.click()
        self.page.wait_for_selector("#chatTyping", state="detached")
        self.page.wait_for_timeout(250)

    def confirm(self) -> None:
        self.page.locator("#chatLog [data-confirm]").last.click()
        self.page.wait_for_timeout(250)

    def new(self) -> None:
        self.page.evaluate(f"go({DAY}); ThreadPilotChat.reset()")
        self.page.click("#chatClear")
        self.page.wait_for_timeout(200)

    def chat(self, name: str, header: bool = False) -> None:
        """The conversation from the first question to the last answer (with the chat header if asked)."""
        self.page.evaluate("document.querySelector('#chatLog').scrollTop = 1e6")
        self.page.wait_for_timeout(150)
        box = self.page.evaluate("""(header) => { const panel = document.querySelector('#chatPanel').getBoundingClientRect(),
            log = document.querySelector('#chatLog'), first = log.querySelector('.msg.user'), last = log.lastElementChild;
            const top = header ? panel.y : first.getBoundingClientRect().top - 10, bottom = last.getBoundingClientRect().bottom + 8;
            return {x: panel.x, y: top, width: panel.width, height: bottom - top}; }""", header)
        self.page.screenshot(path=str(self.out / f"{name}.png"), clip=box)
        self.names.append(name)

    def whole(self, name: str) -> None:
        self.page.screenshot(path=str(self.out / f"{name}.png"))
        self.names.append(name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": TALL}, device_scale_factor=2)
        page.goto(DEMO.as_uri())
        page.wait_for_selector("#riskCard .rk-col")
        page.evaluate(f"go({DAY})")
        page.wait_for_timeout(300)
        s = Shots(page, args.out)

        page.set_viewport_size({"width": 1280, "height": 860})
        s.whole("01_briefing")                                            # the morning page, chat closed
        page.set_viewport_size({"width": 1280, "height": TALL})
        page.click("#chatFab")
        page.wait_for_selector("#chatPanel:not([hidden])")

        s.new(); s.ask("How is the TrendCart order doing?"); s.chat("02_asks_which")
        s.click_chip("ORD-020"); s.chat("02b_then_answers")

        s.new()
        for q in ("When is ORD-120 due?", "who is the customer?", "how many pieces?"):
            s.ask(q)
        s.chat("03_follow_ups")

        s.new(); s.ask("What's our revenue this month?"); s.ask("Why did washing drop yesterday?"); s.chat("04_refuses_and_partial")

        s.new(); s.ask("Can we take 800 hoodies by the 25th?"); s.chat("05_feasibility")

        s.new(); s.ask("Chase ORD-120"); s.chat("06_confirmation_card")
        s.confirm(); s.ask("Delete ORD-005"); s.chat("07_logged_and_refused")

        s.new(); s.ask("Tell me if ORD-120 hasn't moved by Friday"); s.confirm()
        page.set_viewport_size({"width": 1280, "height": 860})
        page.evaluate(f"go({DAY + 1})")                                   # the next morning's briefing: the watch fires
        page.wait_for_timeout(350)
        page.set_viewport_size({"width": 1280, "height": 860})
        s.whole("08_watch_fired")
        browser.close()
    print("wrote " + ", ".join(f"{n}.png" for n in s.names) + f" to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
