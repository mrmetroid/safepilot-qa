"""Pure parts of the sandbox runner protocol (Section 3.4 / 3.5)."""

import io
import json

import pytest

JOB = {
    "run_id": "r1",
    "box_id": "box1",
    "target_url": "https://example.com",
    "persona": "happy_path",
    "viewport": {"width": 1280, "height": 800},
}


def test_validate_job_fills_defaults(runner_module):
    job = runner_module.validate_job(dict(JOB))
    assert job["max_steps"] == 16
    assert "done" in job["allowed_actions"]


@pytest.mark.parametrize("missing", ["run_id", "viewport", "persona"])
def test_validate_job_rejects_missing_fields(runner_module, missing):
    job = {k: v for k, v in JOB.items() if k != missing}
    with pytest.raises(ValueError):
        runner_module.validate_job(job)


def test_parse_action_accepts_allowed(runner_module):
    allowed = runner_module.DEFAULT_ALLOWED_ACTIONS
    action = runner_module.parse_action('{"action": "click", "selector": "#buy"}', allowed)
    assert action["selector"] == "#buy"


@pytest.mark.parametrize(
    "raw",
    [
        {"action": "evaluate", "value": "process.env"},
        {"action": "hold_for_approval"},  # the control plane holds; the runner never sees it
        {"action": "click"},
        {"action": "goto", "url": "javascript:alert(1)"},
        {"action": "goto", "url": "file:///etc/passwd"},
        {"action": "press"},
        [1, 2],
    ],
)
def test_parse_action_rejects(runner_module, raw):
    with pytest.raises(ValueError):
        runner_module.parse_action(raw, runner_module.DEFAULT_ALLOWED_ACTIONS)


def test_events_are_single_json_lines_with_required_keys(runner_module):
    out = io.StringIO()
    runner = runner_module.Runner(runner_module.validate_job(dict(JOB)), out=out)
    runner.emit("console", level="error", message="boom")
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert {"type", "run_id", "box_id", "ts"} <= event.keys()


def test_bad_job_on_stdin_emits_runner_error(runner_module, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"box_id": "box1"}\n'))
    assert runner_module.main(["runner.py", "-"]) == 2
    event = json.loads(capsys.readouterr().out)
    assert event["type"] == "runner_error"
