"""Hand-written fakes. No mocking library: these are small real implementations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from safepilot_ci.pipeline import Command


@dataclass(frozen=True)
class Call:
    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]


@dataclass
class FakeRunner:
    """Records every command. Fails a command when its argv contains a configured word."""

    fail_on: Mapping[str, int] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)

    def run(self, command: Command, cwd: Path, env: Mapping[str, str]) -> int:
        self.calls.append(Call(command.argv, cwd, dict(env)))
        for word, code in self.fail_on.items():
            if word in command.argv:
                return code
        return 0

    def ran(self, word: str) -> bool:
        return any(word in call.argv for call in self.calls)


class FakeClock:
    """Advances a fixed amount on every read."""

    def __init__(self, step: float = 1.5) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


def make_repo(root: Path, *paths: str) -> Path:
    """Create a fake repo tree: spec markers plus the given files or dirs (dir if no dot)."""
    (root / "BUILD_SPEC.md").write_text("spec")
    (root / "AGENTS.md").write_text("agents")
    for rel in paths:
        target = root / rel
        if "." in Path(rel).name:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("")
        else:
            target.mkdir(parents=True, exist_ok=True)
    return root


FULL_REPO = (
    "backend/app",
    "backend/requirements.txt",
    "backend/tests/test_smoke.py",
    "sandbox-runner/Dockerfile",
    "demo-target/Dockerfile",
    "frontend/package.json",
)
