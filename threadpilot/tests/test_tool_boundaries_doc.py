"""docs/tool_boundaries.md must show what the chat does now, and every tool it names must exist.

The table in that page is recorded from the real dashboard chat by scripts/record_boundaries.py, which also fails if the chat uses a
different tool than the case says. This test records it again on the page built from the current source and compares. If it fails after
you changed the chat, run `python scripts/record_boundaries.py`, read the diff in the page (it is what a manager would now see), commit it.
"""
import importlib.util
import re


def recorder():
    from conftest import ROOT
    spec = importlib.util.spec_from_file_location("record_boundaries", ROOT / "scripts" / "record_boundaries.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_boundaries_page_matches_the_chat(page):
    rec = recorder()
    assert rec.render_doc(rec.render(page)) == rec.DOC.read_text(encoding="utf-8"), \
        "docs/tool_boundaries.md is out of date: run python scripts/record_boundaries.py"


def test_every_case_uses_the_tool_it_names_and_not_its_neighbour(page):
    rec = recorder()
    groups = rec.run_cases(page)           # raises AssertionError naming the question if the chat used a different tool
    assert sum(len(rows) for _, rows in groups) >= 20


def test_tools_named_in_the_page_are_in_the_tool_spec_and_in_the_chat(page):
    from conftest import ROOT
    rec = recorder()
    spec = (ROOT / "docs" / "tool_spec.md").read_text(encoding="utf-8")
    page_text = rec.DOC.read_text(encoding="utf-8")
    in_spec = set(re.findall(r"^\| [BD]\d+ \| `([a-z_]+)`", spec, re.M))
    chat_tools = set(page.evaluate("Object.keys(ThreadPilotChat.tools)"))
    named = set(re.findall(r"`([a-z]+_[a-z_]+)`", page_text)) - {"run_sql", "dashboard_service", "compose_briefing", "record_boundaries"}
    unknown = {n for n in named if n not in in_spec and n not in chat_tools and not n.startswith(("tests", "scripts", "docs", "evaluation"))}
    # words in backticks that are not tools: intents, file names, function names
    unknown -= {"briefing.today", "data.unavailable", "order.prioritize"}
    unknown -= {"deviation", "save_note", "create_reminder"}     # the three OLD names, mentioned in the page as the ones that were corrected
    unknown = {n for n in unknown if "." not in n and "/" not in n}
    assert not unknown, f"the page names tools that are in neither docs/tool_spec.md nor the chat: {sorted(unknown)}"
    assert chat_tools <= in_spec, f"chat tools missing from docs/tool_spec.md: {sorted(chat_tools - in_spec)}"
