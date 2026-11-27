"""The CI plan as data: stages of steps, each a list of commands. Nothing runs here."""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field

from safepilot_ci.repo import RepoLayout

STAGES = ("lint", "test", "frontend", "images")

SANDBOX_IMAGE = "safepilot-sandbox:ci"
DEMO_TARGET_IMAGE = "safepilot-demo-target:ci"
FORBIDDEN_ENV_KEYS = ("VULTR_INFERENCE_API_KEY", "VULTR_API_KEY")
CANARY = "ci-canary-must-not-reach-the-sandbox"

# Section 3.2 / 8.4 flags. `--network none` is stricter than the runtime bridge, which is
# fine for a probe that needs no network.
SANDBOX_FLAGS = (
    "--read-only",
    "--tmpfs",
    "/tmp:rw,noexec,nosuid,size=128m",
    "--memory",
    "512m",
    "--memory-swap",
    "512m",
    "--cpus",
    "1",
    "--pids-limit",
    "128",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges:true",
    "--network",
    "none",
)

# Runs inside the sandbox image. Fails on leaked secrets, a writable rootfs, or root.
ISOLATION_PROBE = """
import json, os, pathlib, sys
leaked = [k for k in {keys!r} if k in os.environ]
# Check the mount flag, not a write: a non-root user is denied writes either way.
rootfs_read_only = bool(os.statvfs("/").f_flag & os.ST_RDONLY)
pathlib.Path("/tmp/ci-probe").write_text("x")
import playwright  # noqa: F401
report = {{"env_keys": sorted(os.environ), "leaked": leaked,
          "rootfs_read_only": rootfs_read_only, "uid": os.getuid()}}
print(json.dumps(report))
sys.exit(1 if leaked or not rootfs_read_only or os.getuid() == 0 else 0)
""".strip().format(keys=FORBIDDEN_ENV_KEYS)


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]
    cwd: str = "."  # relative to the repo root
    env: Mapping[str, str] = field(default_factory=dict)

    def display(self) -> str:
        parts = [
            f"<script: {arg.count(chr(10)) + 1} lines>" if "\n" in arg else shlex.quote(arg)
            for arg in self.argv
        ]
        line = " ".join(parts)
        return f"(cd {self.cwd} && {line})" if self.cwd != "." else line


@dataclass(frozen=True)
class Step:
    name: str
    stage: str
    commands: tuple[Command, ...] = ()
    skip_reason: str | None = None


def build_pipeline(layout: RepoLayout, python: str) -> list[Step]:
    """All steps in run order. `python` is the interpreter that has ruff and pytest."""
    return [
        *_lint_steps(layout, python),
        *_test_steps(layout, python),
        *_frontend_steps(layout),
        *_image_steps(layout),
    ]


def select_stages(steps: list[Step], stages: list[str]) -> list[Step]:
    unknown = sorted(set(stages) - set(STAGES))
    if unknown:
        raise ValueError(f"unknown stage(s): {', '.join(unknown)}; choose from {', '.join(STAGES)}")
    wanted = set(stages) or set(STAGES)
    return [step for step in steps if step.stage in wanted]


def _lint_steps(layout: RepoLayout, python: str) -> list[Step]:
    steps = [
        Step(
            "ruff: ci project",
            "lint",
            (
                Command((python, "-m", "ruff", "check", "ci")),
                Command((python, "-m", "ruff", "format", "--check", "ci")),
            ),
        )
    ]
    if layout.python_paths:
        # Default rule set: the app code has no ruff config of its own yet.
        steps.append(
            Step(
                "ruff: app code",
                "lint",
                (Command((python, "-m", "ruff", "check", "--isolated", *layout.python_paths)),),
            )
        )
    return steps


def _test_steps(layout: RepoLayout, python: str) -> list[Step]:
    steps = [Step("pytest: ci project", "test", (Command((python, "-m", "pytest", "-q"), "ci"),))]
    if not layout.backend_requirements:
        return [
            *steps,
            Step("backend import smoke", "test", skip_reason="no backend/requirements.txt"),
        ]
    with_backend = ("uv", "run", "--no-project", "--python", "3.12")
    with_backend += ("--with-requirements", "requirements.txt")
    steps.append(
        Step(
            "backend import smoke",
            "test",
            (Command((*with_backend, "python", "-c", "import app.main"), "backend"),),
        )
    )
    if layout.backend_tests:
        pytest_cmd = (*with_backend, "--with", "pytest", "python", "-m", "pytest", "-q")
        steps.append(
            Step(
                "pytest: backend (no docker)",
                "test",
                (Command((*pytest_cmd, "-m", "not docker"), "backend"),),
            )
        )
    else:
        steps.append(Step("pytest: backend", "test", skip_reason="no backend/tests yet"))
    return steps


def _frontend_steps(layout: RepoLayout) -> list[Step]:
    if not layout.frontend:
        return [Step("frontend build", "frontend", skip_reason="no frontend/package.json")]
    return [
        Step(
            "frontend build",
            "frontend",
            (
                Command(("npm", "ci", "--no-fund", "--no-audit"), "frontend"),
                Command(("npm", "run", "build"), "frontend"),
            ),
        )
    ]


def _image_steps(layout: RepoLayout) -> list[Step]:
    steps: list[Step] = []
    if layout.demo_target:
        steps.append(
            Step(
                "docker build: demo-target",
                "images",
                (Command(("docker", "build", "-t", DEMO_TARGET_IMAGE, "demo-target")),),
            )
        )
    if not layout.sandbox_runner:
        return [*steps, Step("sandbox isolation", "images", skip_reason="no sandbox-runner")]
    steps.append(
        Step(
            "docker build: sandbox-runner",
            "images",
            (Command(("docker", "build", "-t", SANDBOX_IMAGE, "sandbox-runner")),),
        )
    )
    canaries = {key: CANARY for key in FORBIDDEN_ENV_KEYS}
    probe = ("docker", "run", "--rm", *SANDBOX_FLAGS, "--entrypoint", "python", SANDBOX_IMAGE)
    steps.append(
        Step(
            "sandbox isolation (Section 8.4)",
            "images",
            # The canaries are set on the host side of `docker run` on purpose: the probe
            # fails if they ever show up inside the container.
            (Command((*probe, "-c", ISOLATION_PROBE), env=canaries),),
        )
    )
    return steps
