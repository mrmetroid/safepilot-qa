import sys

from safepilot_ci.executor import COMMAND_NOT_FOUND, SubprocessRunner, execute
from safepilot_ci.pipeline import Command, Step
from tests.fakes import FakeClock, FakeRunner

STEPS = [
    Step("one", "lint", (Command(("tool", "a")), Command(("tool", "b")))),
    Step("two", "test", (Command(("tool", "boom"), "backend", {"X": "1"}),)),
    Step("three", "test", (Command(("tool", "c")),)),
    Step("four", "images", skip_reason="nothing to build"),
]


def run(tmp_path, runner, **kwargs):
    log: list[str] = []
    report = execute(
        STEPS,
        runner,
        tmp_path,
        base_env={"BASE": "y"},
        log=log.append,
        clock=FakeClock(),
        **kwargs,
    )
    return report, log


def test_all_green(tmp_path):
    runner = FakeRunner()
    report, _ = run(tmp_path, runner)
    assert report.ok
    assert [r.status for r in report.results] == ["passed", "passed", "passed", "skipped"]
    assert [c.argv[1] for c in runner.calls] == ["a", "b", "boom", "c"]
    assert report.results[0].seconds == 1.5


def test_command_gets_cwd_and_merged_env(tmp_path):
    runner = FakeRunner()
    run(tmp_path, runner)
    call = runner.calls[2]
    assert call.cwd == tmp_path / "backend"
    assert call.env == {"BASE": "y", "X": "1"}


def test_stops_after_first_failure(tmp_path):
    runner = FakeRunner(fail_on={"boom": 3})
    report, _ = run(tmp_path, runner)
    assert not report.ok
    assert [r.status for r in report.results] == ["passed", "failed", "skipped", "skipped"]
    assert report.results[1].detail == "exit 3: tool"
    assert report.results[2].detail == "earlier step failed"
    assert not runner.ran("c")


def test_failing_command_stops_its_own_step(tmp_path):
    runner = FakeRunner(fail_on={"a": 1})
    report, _ = run(tmp_path, runner, keep_going=True)
    assert not runner.ran("b")
    assert report.results[0].status == "failed"


def test_keep_going_runs_later_steps(tmp_path):
    runner = FakeRunner(fail_on={"boom": 3})
    report, _ = run(tmp_path, runner, keep_going=True)
    assert [r.status for r in report.results] == ["passed", "failed", "passed", "skipped"]
    assert runner.ran("c")


def test_github_groups_and_error_annotation(tmp_path):
    _, log = run(tmp_path, FakeRunner(fail_on={"boom": 2}), github=True)
    assert log.count("::endgroup::") == 2
    assert "::group::one" in log
    assert any(line.startswith("::error title=CI step failed::two") for line in log)


def test_plain_log_has_no_workflow_commands(tmp_path):
    _, log = run(tmp_path, FakeRunner())
    assert not any(line.startswith("::") for line in log)
    assert "==> [lint] one" in log


def test_summary_lines(tmp_path):
    report, _ = run(tmp_path, FakeRunner(fail_on={"boom": 3}))
    lines = report.summary_lines()
    assert lines[-1] == "CI FAILED"
    assert lines[1].startswith("FAILED") and "[test] two" in lines[1]


def test_subprocess_runner_returns_real_exit_codes(tmp_path):
    runner = SubprocessRunner()
    env = {"PATH": "/usr/bin:/bin"}
    exit_three = Command((sys.executable, "-c", "import sys; sys.exit(3)"))
    assert runner.run(exit_three, tmp_path, env) == 3
    write_cwd = Command((sys.executable, "-c", "open('here', 'w').write('x')"))
    assert runner.run(write_cwd, tmp_path, env) == 0
    assert (tmp_path / "here").exists()


def test_subprocess_runner_reports_missing_binary(tmp_path):
    missing = Command(("definitely-not-a-real-binary-xyz",))
    assert SubprocessRunner().run(missing, tmp_path, {"PATH": ""}) == COMMAND_NOT_FOUND
