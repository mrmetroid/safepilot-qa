from typer.testing import CliRunner

from safepilot_ci.cli import build_app
from tests.fakes import FULL_REPO, FakeRunner, make_repo


def invoke(runner, *args, env=None):
    app = build_app(runner_factory=lambda: runner, python="/venv/bin/python")
    return CliRunner().invoke(app, list(args), env=env or {"GITHUB_ACTIONS": ""})


def test_run_all_stages_green(tmp_path):
    repo = make_repo(tmp_path, *FULL_REPO)
    fake = FakeRunner()
    result = invoke(fake, "run", "--root", str(repo))
    assert result.exit_code == 0, result.output
    assert "CI PASSED" in result.output
    assert fake.ran("ruff") and fake.ran("npm") and fake.ran("docker")


def test_run_selected_stage_only(tmp_path):
    repo = make_repo(tmp_path, *FULL_REPO)
    fake = FakeRunner()
    result = invoke(fake, "run", "lint", "--root", str(repo))
    assert result.exit_code == 0
    assert fake.ran("ruff") and not fake.ran("docker") and not fake.ran("npm")


def test_failure_sets_exit_code_and_summary(tmp_path):
    repo = make_repo(tmp_path, *FULL_REPO)
    result = invoke(FakeRunner(fail_on={"npm": 1}), "run", "--root", str(repo))
    assert result.exit_code == 1
    assert "CI FAILED" in result.output
    assert "SKIPPED" in result.output  # images stage after the failure


def test_unknown_stage_is_a_usage_error(tmp_path):
    repo = make_repo(tmp_path, *FULL_REPO)
    fake = FakeRunner()
    result = invoke(fake, "run", "deploy", "--root", str(repo))
    assert result.exit_code == 2
    assert fake.calls == []


def test_github_mode_from_env(tmp_path):
    repo = make_repo(tmp_path, *FULL_REPO)
    result = invoke(
        FakeRunner(), "run", "lint", "--root", str(repo), env={"GITHUB_ACTIONS": "true"}
    )
    assert "::group::" in result.output


def test_list_runs_nothing(tmp_path):
    repo = make_repo(tmp_path, *FULL_REPO)
    fake = FakeRunner()
    result = invoke(fake, "list", "--root", str(repo))
    assert result.exit_code == 0
    assert "[images] sandbox isolation (Section 8.4)" in result.output
    assert fake.calls == []


def test_root_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke(FakeRunner(), "list")
    assert result.exit_code == 2
