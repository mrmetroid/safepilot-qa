from click.exceptions import Abort

from app.cli_format import (
    format_event,
    resolve_approval,
    strip_binary,
    summary_lines,
    verdict_exit_code,
)

NAMES = {"box1": "Happy Path", "box3": "Chaos Gremlin"}
APPROVAL = {"type": "approval_required", "box_id": "box1", "action": "click",
            "selector": "#place-order", "page_url": "http://demo-target/checkout", "reason": "Irreversible"}


class FakeHuman:
    """Answers prompts from a script and remembers what it was asked."""

    def __init__(self, answer=None, raises=None):
        self.answer, self.raises, self.prompts = answer, raises, []

    def __call__(self, prompt: str) -> bool:
        self.prompts.append(prompt)
        if self.raises:
            raise self.raises
        return self.answer


def test_only_an_explicit_yes_approves():
    human = FakeHuman(answer=True)
    assert resolve_approval(APPROVAL, NAMES, "ask", human) == "approve"
    assert "#place-order" in human.prompts[0] and "Happy Path" in human.prompts[0]


def test_no_or_non_bool_answers_block():
    assert resolve_approval(APPROVAL, NAMES, "ask", FakeHuman(answer=False)) == "block"
    assert resolve_approval(APPROVAL, NAMES, "ask", FakeHuman(answer="yes")) == "block"


def test_no_answer_blocks():
    for exc in (EOFError(), KeyboardInterrupt(), Abort(), OSError()):
        assert resolve_approval(APPROVAL, NAMES, "ask", FakeHuman(raises=exc)) == "block"


def test_block_mode_never_asks():
    human = FakeHuman(answer=True)
    assert resolve_approval(APPROVAL, NAMES, "block", human) == "block"
    assert human.prompts == []


def test_verdict_exit_codes():
    assert verdict_exit_code("SHIP IT") == 0
    assert verdict_exit_code("DO NOT SHIP") == 1
    assert verdict_exit_code(None) == 2


def test_format_events():
    assert format_event({"type": "box_stats", "box_id": "box1"}, NAMES) is None
    assert format_event({"type": "screenshot", "box_id": "box1"}, NAMES) is None
    step = format_event({"type": "step_update", "box_id": "box1", "step": 2, "log": "click #buy",
                         "ok": False}, NAMES)
    assert step == "[box1 Happy Path] step 2 click #buy  [retry]"
    assert "APPROVAL REQUIRED" in format_event(APPROVAL, NAMES)
    receipt = format_event({"type": "containment_triggered", "box_id": "box3",
                            "trigger_reason": "cpu_limit_exceeded", "secrets_exposed": 0,
                            "host_impact": "none", "container_destroyed": True}, NAMES)
    assert receipt.startswith("[box3 Chaos Gremlin] Containment Receipt")
    assert 'secrets_exposed: 0' in receipt and "container_destroyed: true" in receipt
    assert format_event({"type": "something_new", "box_id": "box9"}, NAMES) == "[box9] something_new"


def test_strip_binary_and_summary():
    assert "data_base64" not in strip_binary({"type": "screenshot", "data_base64": "AAAA"})
    lines = summary_lines({"verdict": "DO NOT SHIP", "headline": "Bad CTA.",
                           "results": [{"box_id": "box1", "name": "Happy Path", "status": "blocked",
                                        "steps": 4, "approval": "block"}]})
    assert lines[0] == "DO NOT SHIP" and lines[1] == "Bad CTA."
    assert "approval=block" in lines[2]
