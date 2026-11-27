"""What the repository contains. Steps are planned from this, not hard-coded."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT_MARKERS = ("BUILD_SPEC.md", "AGENTS.md")


class RepoNotFound(Exception):
    pass


def find_repo_root(start: Path) -> Path:
    """Walk up from `start` to the directory that holds the Canary Swarm spec files."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if all((candidate / marker).is_file() for marker in ROOT_MARKERS):
            return candidate
    raise RepoNotFound(f"no Canary Swarm repo root above {start}")


@dataclass(frozen=True)
class RepoLayout:
    root: Path
    python_paths: tuple[str, ...]
    backend_requirements: bool
    backend_tests: bool
    frontend: bool
    sandbox_runner: bool
    demo_target: bool

    @classmethod
    def scan(cls, root: Path) -> RepoLayout:
        def exists(rel: str) -> bool:
            return (root / rel).exists()

        python_paths = tuple(p for p in ("backend/app", "sandbox-runner") if exists(p))
        return cls(
            root=root,
            python_paths=python_paths,
            backend_requirements=exists("backend/requirements.txt"),
            # Stale dirs (only __pycache__) must not count as a test suite.
            backend_tests=any((root / "backend/tests").glob("**/test_*.py")),
            frontend=exists("frontend/package.json"),
            sandbox_runner=exists("sandbox-runner/Dockerfile"),
            demo_target=exists("demo-target/Dockerfile"),
        )
