import pytest

from safepilot_ci.pipeline import (
    CANARY,
    FORBIDDEN_ENV_KEYS,
    SANDBOX_IMAGE,
    STAGES,
    build_pipeline,
    select_stages,
)
from safepilot_ci.repo import RepoLayout
from tests.fakes import FULL_REPO, make_repo

PY = "/venv/bin/python"


def steps_for(tmp_path, *paths):
    return build_pipeline(RepoLayout.scan(make_repo(tmp_path, *paths)), PY)


def by_name(steps):
    return {step.name: step for step in steps}


def test_stages_run_in_declared_order(tmp_path):
    stages = [step.stage for step in steps_for(tmp_path, *FULL_REPO)]
    assert stages == sorted(stages, key=STAGES.index)
    assert set(stages) == set(STAGES)


def test_lint_uses_ruff_from_the_ci_interpreter(tmp_path):
    steps = by_name(steps_for(tmp_path, *FULL_REPO))
    app_lint = steps["ruff: app code"].commands[0].argv
    assert app_lint[:4] == (PY, "-m", "ruff", "check")
    assert app_lint[-2:] == ("backend/app", "sandbox-runner")
    ci_lint = [c.argv for c in steps["ruff: ci project"].commands]
    assert (PY, "-m", "ruff", "format", "--check", "ci") in ci_lint


def test_backend_tests_skip_docker_marked_tests(tmp_path):
    step = by_name(steps_for(tmp_path, *FULL_REPO))["pytest: backend (no docker)"]
    command = step.commands[0]
    assert command.cwd == "backend"
    assert command.argv[-2:] == ("-m", "not docker")
    assert "requirements.txt" in command.argv


def test_missing_parts_become_skipped_steps_not_silent_gaps(tmp_path):
    steps = by_name(steps_for(tmp_path, "backend/app", "backend/requirements.txt"))
    assert steps["pytest: backend"].skip_reason == "no backend/tests yet"
    assert steps["frontend build"].skip_reason
    assert steps["sandbox isolation"].skip_reason
    assert not steps["backend import smoke"].skip_reason


def test_sandbox_probe_uses_spec_flags_and_host_side_canaries(tmp_path):
    steps = by_name(steps_for(tmp_path, *FULL_REPO))
    build = steps["docker build: sandbox-runner"].commands[0].argv
    assert build == ("docker", "build", "-t", SANDBOX_IMAGE, "sandbox-runner")
    probe = steps["sandbox isolation (Section 8.4)"].commands[0]
    argv = " ".join(probe.argv)
    for flag in (
        "--read-only",
        "--memory 512m",
        "--memory-swap 512m",
        "--cpus 1",
        "--pids-limit 128",
        "--cap-drop ALL",
        "no-new-privileges:true",
        "/tmp:rw,noexec,nosuid,size=128m",
    ):
        assert flag in argv
    for forbidden in ("--privileged", "--network host", "-e ", "--env", "docker.sock", "-v "):
        assert forbidden not in argv
    assert probe.env == {key: CANARY for key in FORBIDDEN_ENV_KEYS}
    assert all(key in probe.argv[-1] for key in FORBIDDEN_ENV_KEYS)


def test_select_stages(tmp_path):
    steps = steps_for(tmp_path, *FULL_REPO)
    assert {s.stage for s in select_stages(steps, ["lint"])} == {"lint"}
    assert select_stages(steps, []) == steps
    with pytest.raises(ValueError, match="deploy"):
        select_stages(steps, ["deploy"])


def test_display_quotes_args_and_collapses_scripts():
    from safepilot_ci.pipeline import Command

    cmd = Command(("pytest", "-m", "not docker", "-c", "a\nb\nc"), "backend")
    assert cmd.display() == "(cd backend && pytest -m 'not docker' -c <script: 3 lines>)"


def test_probe_checks_the_mount_flag_not_write_permission():
    from safepilot_ci.pipeline import ISOLATION_PROBE

    assert "ST_RDONLY" in ISOLATION_PROBE
    compile(ISOLATION_PROBE, "probe", "exec")
