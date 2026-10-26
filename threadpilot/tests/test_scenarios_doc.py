"""docs/conversation_scenarios.md must show what the chat does now.

The transcripts in that page are recorded from the real dashboard chat by scripts/record_scenarios.py. This test records them again
on the page built from the current source and compares. If it fails after you changed the chat, run
`python scripts/record_scenarios.py`, read the diff in the page (it is the change a user would see), and commit it.
"""
import importlib.util


def recorder():
    from conftest import ROOT
    spec = importlib.util.spec_from_file_location("record_scenarios", ROOT / "scripts" / "record_scenarios.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_scenarios_page_matches_the_chat(page):
    rec = recorder()
    assert rec.render_doc(rec.record(page)) == rec.DOC.read_text(encoding="utf-8"), \
        "docs/conversation_scenarios.md is out of date: run python scripts/record_scenarios.py"


def test_every_scenario_is_in_the_page_and_shows_what_it_claims(page):
    rec = recorder()
    generated = rec.record(page)
    for sc in rec.SCENARIOS:
        assert f"### {sc['id']}. {sc['title']}" in generated
    # the behaviours the page exists to show, in the recorded text itself
    assert "Which one do you mean?" in generated                                   # S2 asks instead of guessing
    assert generated.count("asks a question instead of answering") >= 2             # S2 and the missing date in S5
    assert "Nothing is sent until you confirm." in generated                        # S6 preview before action
    assert "Worst case:" in generated                                               # every card states its worst case
    assert "I can't cancel, delete or change orders" in generated                   # S6 refusal
    assert "so I cannot say why" in generated                                       # S4 gives the number, not a cause
    assert "not a commitment" in generated                                          # S5 estimate wording
    assert "fired:" in generated and "cleared:" in generated                        # S7 and S8 end differently
    assert "None" not in generated.replace("None expected", "")                     # no leaked null in the transcript


def test_recorded_times_are_masked(page):
    rec = recorder()
    generated = rec.record(page)
    assert "HH:MM" in generated, "the confirmation times must be masked or the page would change every minute"
