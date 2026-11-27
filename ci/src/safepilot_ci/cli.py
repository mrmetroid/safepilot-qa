"""`safepilot-ci`: the single entry point for CI, locally and in GitHub Actions.

uv run --project ci safepilot-ci run              # every stage
uv run --project ci safepilot-ci run lint test    # selected stages
uv run --project ci safepilot-ci list             # show the plan
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from safepilot_ci.executor import CommandRunner, SubprocessRunner, execute
from safepilot_ci.pipeline import STAGES, build_pipeline, select_stages
from safepilot_ci.repo import RepoLayout, RepoNotFound, find_repo_root

StageArg = Annotated[
    list[str] | None,
    typer.Argument(help=f"Stages to run: {', '.join(STAGES)}. Default: all, in that order."),
]
RootOpt = Annotated[
    Path | None, typer.Option(help="Repository root. Default: found from the current directory.")
]


def build_app(
    runner_factory: Callable[[], CommandRunner] = SubprocessRunner,
    python: str = sys.executable,
) -> typer.Typer:
    """Build the CLI. Tests pass a fake runner factory; production uses real subprocesses."""
    app = typer.Typer(help="SafePilot QA CI pipeline.", no_args_is_help=True)

    def plan(root: Path | None, stages: list[str] | None):
        try:
            repo_root = root.resolve() if root else find_repo_root(Path.cwd())
        except RepoNotFound as exc:
            typer.secho(str(exc), fg="red", err=True)
            raise typer.Exit(2) from exc
        try:
            steps = select_stages(build_pipeline(RepoLayout.scan(repo_root), python), stages or [])
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="STAGES") from exc
        return repo_root, steps

    @app.command("list")
    def list_steps(stages: StageArg = None, root: RootOpt = None) -> None:
        """Print the planned steps and their commands without running anything."""
        _, steps = plan(root, stages)
        for step in steps:
            if step.skip_reason:
                typer.echo(f"[{step.stage}] {step.name}: skipped ({step.skip_reason})")
                continue
            typer.echo(f"[{step.stage}] {step.name}")
            for command in step.commands:
                typer.echo(f"    $ {command.display()}")

    @app.command("run")
    def run(
        stages: StageArg = None,
        root: RootOpt = None,
        keep_going: Annotated[
            bool, typer.Option("--keep-going", help="Run later steps after a failure.")
        ] = False,
        github: Annotated[
            bool,
            typer.Option(
                envvar="GITHUB_ACTIONS", help="Emit GitHub Actions log groups and annotations."
            ),
        ] = False,
    ) -> None:
        """Run the pipeline. Exit code 1 if any step failed."""
        repo_root, steps = plan(root, stages)
        report = execute(
            steps,
            runner_factory(),
            repo_root,
            keep_going=keep_going,
            github=github,
            log=typer.echo,
        )
        typer.echo("")
        for line in report.summary_lines():
            typer.echo(line)
        raise typer.Exit(0 if report.ok else 1)

    return app


app = build_app()
