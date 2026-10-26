"""The script that makes the slide screenshots must keep working as the interface changes.

It types real questions into the real chat box, so a renamed button or a changed id breaks it. This test runs it into a temporary
folder and checks that every picture exists, is a real PNG and is not nearly empty. It does not compare pixels: the pictures contain the time of day.
"""
import struct
import subprocess
import sys

import pytest
from conftest import ROOT

EXPECTED = ["01_briefing", "02_asks_which", "02b_then_answers", "03_follow_ups", "04_refuses_and_partial", "05_feasibility",
            "06_confirmation_card", "07_logged_and_refused", "08_watch_fired"]


def test_capture_script_makes_every_screenshot(tmp_path):
    pytest.importorskip("playwright.sync_api")
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "capture_screenshots.py"), "--out", str(tmp_path)],
                         cwd=ROOT, capture_output=True, text=True, timeout=180)
    if "Executable doesn't exist" in run.stderr or "BrowserType.launch" in run.stderr:
        pytest.skip("headless browser not available")
    assert run.returncode == 0, run.stderr[-800:]
    for name in EXPECTED:
        f = tmp_path / f"{name}.png"
        assert f.exists(), name
        data = f.read_bytes()
        width, height = struct.unpack(">II", data[16:24])
        assert data[:8] == b"\x89PNG\r\n\x1a\n" and width >= 800 and height >= 600, f"{name}: not a usable PNG ({width}x{height})"
        assert len(data) > 40_000, f"{name} is only {len(data)} bytes: probably blank"
