"""SafePilot QA developer CLI (`scripts/safepilot` or `python -m app.cli` from backend/).

The CLI is a control plane, not a sandbox: it drives the same orchestrator as the dashboard
(run_manager, docker_runner, policy) and never runs Playwright in-process. Approvals come
from a human at the terminal. There is deliberately no auto-approve option.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import uuid
from pathlib import Path
from typing import Annotated, Any

import typer

from .cli_format import (
    ApprovalMode,
    format_event,
    resolve_approval,
    strip_binary,
    summary_lines,
    verdict_exit_code,
)
from .config import settings
from .health import health_report
from .orch import docker_runner, policy
from .orch import run_manager as rm
from .orch.isolation import isolation_problems

app = typer.Typer(help="SafePilot QA developer CLI.", no_args_is_help=True)
sandbox_app = typer.Typer(help="Inspect and clean up sandbox containers.", no_args_is_help=True)
app.add_typer(sandbox_app, name="sandbox")


def _require_docker() -> None:
    err = docker_runner.ping()
    if err:
        typer.secho(f"Docker is not reachable: {err}", fg="red", err=True)
        raise typer.Exit(2)


# ----------------------------------------------------------------------------- health
@app.command()
def health(as_json: Annotated[bool, typer.Option("--json", help="Raw JSON.")] = False) -> None:
    """The same report as GET /api/health (Section 6.1)."""
    body = asyncio.run(health_report())
    if as_json:
        typer.echo(json.dumps(body, indent=2))
    else:
        for key in ("control_plane", "docker", "inference"):
            ok = body[key] == "ok"
            detail = (body.get("errors") or {}).get(key, "")
            typer.secho(f"{key:<14} {body[key]:<12} {detail}", fg="green" if ok else "red")
        image = "present" if body["sandbox_image_present"] else "MISSING"
        typer.echo(f"{'sandbox_image':<14} {image:<12} {body['sandbox_image']}")
    raise typer.Exit(0 if body["ok"] else 1)


# ----------------------------------------------------------------------------- sandbox
async def _probe_sandbox() -> tuple[dict[str, Any], bool]:
    """Start one real sandbox through the orchestrator, inspect it, then destroy it."""
    docker_runner.ensure_network()
    sb = docker_runner.Sandbox(f"verify{uuid.uuid4().hex[:8]}", "box0", asyncio.get_running_loop())
    job = {
        "run_id": sb.run_id,
        "box_id": "box0",
        "box_name": "Isolation check",
        "target_url": settings.demo_target_sandbox_url,
        "persona": "chaos_gremlin",
        "viewport": {"width": 1280, "height": 800},
        "max_steps": 1,
        "step_timeout_seconds": settings.step_timeout,
        "allowed_actions": ["done"],
        "initial_action": None,
    }
    try:
        await asyncio.to_thread(sb.start, job)
        info = await asyncio.to_thread(sb.inspect_env)
    finally:
        destroyed = await asyncio.to_thread(sb.destroy)
    return info, destroyed


@sandbox_app.command("verify")
def sandbox_verify() -> None:
    """Start a real sandbox with the production flags and check Section 3 / 8.4 isolation."""
    _require_docker()
    info, destroyed = asyncio.run(_probe_sandbox())
    problems = isolation_problems(info, settings)
    if not destroyed:
        problems.append("container was not destroyed")
    typer.echo(f"env names: {', '.join(info.get('env_names') or []) or '(none)'}")
    host_secrets = len(settings.secret_values())
    typer.echo(f"host secrets present on the control plane: {host_secrets}, "
               f"exposed in sandbox: {info.get('secrets_exposed')}")
    for problem in problems:
        typer.secho(f"FAIL {problem}", fg="red")
    if problems:
        raise typer.Exit(1)
    typer.secho("PASS caps, read-only rootfs, dropped caps, non-root, no secrets, destroyed",
                fg="green")


@sandbox_app.command("sweep")
def sandbox_sweep() -> None:
    """Remove sandbox containers left behind by crashed runs (all runs on this host)."""
    _require_docker()
    typer.echo(f"removed {docker_runner.sweep_leftovers()} sandbox container(s)")


# ----------------------------------------------------------------------------- run
def _ask(prompt: str) -> bool:
    return typer.confirm(prompt, default=False, err=True)


def _save_screenshot(out: Path, run_id: str, ev: dict[str, Any]) -> None:
    folder = out / run_id
    folder.mkdir(parents=True, exist_ok=True)
    ext = "png" if "png" in (ev.get("content_type") or "") else "jpg"
    (folder / f"{ev['box_id']}-step-{ev['step']}.{ext}").write_bytes(
        base64.b64decode(ev["data_base64"])
    )


async def _drive_run(
    mode: str, url: str | None, approvals: ApprovalMode, as_json: bool, out: Path | None
) -> dict[str, Any]:
    docker_runner.ensure_network()
    run = rm.create_run(mode, url)
    queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
    run.subscribers.add(queue)  # before the first await, so no event is missed
    names = {b.box_id: b.name for b in run.boxes.values()}
    typer.echo(f"run {run.run_id} ({mode}) {run.url}", err=as_json)
    try:
        while True:
            ev = await queue.get()
            if out is not None and ev.get("type") == "screenshot" and ev.get("data_base64"):
                _save_screenshot(out, run.run_id, ev)
            if as_json:
                typer.echo(json.dumps(strip_binary(ev)))
            else:
                line = format_event(ev, names)
                if line:
                    typer.echo(line)
            if ev.get("type") == "approval_required":
                decision = await asyncio.to_thread(resolve_approval, ev, names, approvals, _ask)
                if not rm.decide(run, ev["box_id"], decision):
                    typer.echo(f"[{ev['box_id']}] approval no longer pending", err=True)
            if ev.get("type") == "run_verdict":
                return ev
    finally:
        run.subscribers.discard(queue)
        await asyncio.to_thread(docker_runner.remove_run_sandboxes, run.run_id)


@app.command()
def run(
    url: Annotated[str | None, typer.Argument(help="Public http(s) URL to sweep.")] = None,
    preset: Annotated[
        bool, typer.Option("--preset", help="Load the adversarial demo target (3-box swarm).")
    ] = False,
    block_approvals: Annotated[
        bool,
        typer.Option("--block-approvals", help="Block every irreversible action without asking."),
    ] = False,
    out: Annotated[Path | None, typer.Option(help="Save screenshots under OUT/<run_id>/.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="One JSON event per line.")] = False,
) -> None:
    """Run a full sweep in the terminal. Exit 0 = SHIP IT, 1 = DO NOT SHIP, 2 = no verdict."""
    if preset == bool(url):
        raise typer.BadParameter("give either a URL or --preset", param_hint="URL")
    mode = "adversarial_preset" if preset else "custom"
    if url:
        url = url.strip() if "://" in url else "https://" + url.strip()
        reason = policy.validate_public_url(url)
        if reason:
            raise typer.BadParameter(f"URL rejected: {reason}", param_hint="URL")
    _require_docker()
    approvals: ApprovalMode = "ask"
    if block_approvals:
        approvals = "block"
    elif not sys.stdin.isatty():
        typer.echo("stdin is not a terminal: irreversible actions will be blocked.", err=True)
        approvals = "block"
    verdict = asyncio.run(_drive_run(mode, url, approvals, as_json, out))
    if not as_json:
        typer.echo("")
        for i, line in enumerate(summary_lines(verdict)):
            if i == 0:
                typer.secho(line, fg="green" if line == "SHIP IT" else "red", bold=True)
            else:
                typer.echo(line)
        if verdict.get("fix_prompt"):
            typer.echo("\nCursor fix prompt:\n")
            typer.echo(verdict["fix_prompt"])
    raise typer.Exit(verdict_exit_code(verdict.get("verdict")))


if __name__ == "__main__":
    app()
