"""Runs a planned pipeline through a CommandRunner and reports the outcome."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from safepilot_ci.pipeline import Command, Step

Status = Literal["passed", "failed", "skipped"]
COMMAND_NOT_FOUND = 127


class CommandRunner(Protocol):
    def run(self, command: Command, cwd: Path, env: Mapping[str, str]) -> int:
        """Run one command and return its exit code."""
        ...


class SubprocessRunner:
    """The real runner. Output streams straight to the terminal or the Actions log."""

    def run(self, command: Command, cwd: Path, env: Mapping[str, str]) -> int:
        try:
            return subprocess.run(
                list(command.argv), cwd=cwd, env=dict(env), check=False
            ).returncode
        except FileNotFoundError:
            print(f"command not found: {command.argv[0]}", flush=True)
            return COMMAND_NOT_FOUND


@dataclass(frozen=True)
class StepResult:
    name: str
    stage: str
    status: Status
    seconds: float = 0.0
    detail: str = ""


@dataclass
class Report:
    results: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.status != "failed" for r in self.results)

    def summary_lines(self) -> list[str]:
        lines = []
        for r in self.results:
            timing = f"{r.seconds:6.1f}s" if r.status != "skipped" else "       "
            detail = f"  ({r.detail})" if r.detail else ""
            lines.append(f"{r.status.upper():<8}{timing}  [{r.stage}] {r.name}{detail}")
        verdict = "CI PASSED" if self.ok else "CI FAILED"
        return [*lines, verdict]


def execute(
    steps: list[Step],
    runner: CommandRunner,
    root: Path,
    *,
    base_env: Mapping[str, str] | None = None,
    keep_going: bool = False,
    github: bool = False,
    log: Callable[[str], None] = print,
    clock: Callable[[], float] = time.monotonic,
) -> Report:
    """Run steps in order. Stops at the first failure unless keep_going."""
    env_base = dict(os.environ if base_env is None else base_env)
    report = Report()
    stopped = False
    for step in steps:
        if step.skip_reason or stopped:
            reason = step.skip_reason or "earlier step failed"
            report.results.append(StepResult(step.name, step.stage, "skipped", detail=reason))
            continue
        log(f"::group::{step.name}" if github else f"==> [{step.stage}] {step.name}")
        started = clock()
        failed_at: Command | None = None
        exit_code = 0
        for command in step.commands:
            log(f"$ {command.display()}")
            exit_code = runner.run(command, root / command.cwd, {**env_base, **command.env})
            if exit_code != 0:
                failed_at = command
                break
        if github:
            log("::endgroup::")
        seconds = clock() - started
        if failed_at is None:
            report.results.append(StepResult(step.name, step.stage, "passed", seconds))
            continue
        detail = f"exit {exit_code}: {failed_at.argv[0]}"
        report.results.append(StepResult(step.name, step.stage, "failed", seconds, detail))
        if github:
            log(f"::error title=CI step failed::{step.name} ({detail})")
        stopped = not keep_going
    return report
