"""SafePilot QA developer CLI.

Acts as the control plane from a terminal so every piece can be exercised as a developer
tool. It drives sandbox containers only. It never runs Playwright in-process.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import docker
import typer
from docker.errors import DockerException, ImageNotFound

from app.config import REPO_ROOT, load_settings
from app.inference.client import check_inference
from app.models.schemas import BOXES, SandboxJob
from app.orch.docker_runner import (
    FORBIDDEN_ENV_KEYS,
    SandboxSession,
    WallClockExceeded,
    dump_sandbox_env,
    env_secret_keys,
    isolation_problems,
    sweep_leftovers,
)

app = typer.Typer(help="SafePilot QA developer CLI.", no_args_is_help=True)
sandbox_app = typer.Typer(help="Build, run, and verify sandbox containers.", no_args_is_help=True)
app.add_typer(sandbox_app, name="sandbox")


def _docker() -> docker.DockerClient:
    try:
        client = docker.from_env()
        client.ping()
        return client
    except DockerException as exc:
        typer.secho(f"Docker daemon not reachable: {exc}", fg="red", err=True)
        raise typer.Exit(2) from exc


@app.command()
def health(
    as_json: Annotated[bool, typer.Option("--json", help="Print the raw JSON.")] = False,
) -> None:
    """Check Docker, the sandbox image, and Vultr Inference (Section 6.1 shape)."""
    settings = load_settings()
    result: dict[str, Any] = {
        "ok": False,
        "control_plane": "ok",
        "docker": "ok",
        "inference": "ok",
        "inference_model": settings.inference_model,
        "sandbox_image": settings.sandbox_image,
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    try:
        client = docker.from_env()
        client.ping()
        client.images.get(settings.sandbox_image)
    except ImageNotFound:
        result["docker"] = "error"
        result["docker_error"] = f"image {settings.sandbox_image} missing: run `sandbox build`"
    except DockerException as exc:
        result["docker"] = "error"
        result["docker_error"] = str(exc)[:200]
    status, error = check_inference(settings)
    result["inference"] = status
    if error:
        result["inference_error"] = error
    result["ok"] = all(result[k] == "ok" for k in ("control_plane", "docker", "inference"))
    if as_json:
        typer.echo(json.dumps(result, indent=2))
    else:
        for key in ("control_plane", "docker", "inference"):
            color = "green" if result[key] == "ok" else "red"
            detail = result.get(f"{key}_error", "")
            typer.secho(f"{key:<14} {result[key]:<6} {detail}", fg=color)
    raise typer.Exit(0 if result["ok"] else 1)


@sandbox_app.command("build")
def sandbox_build(
    path: Annotated[Path, typer.Option(help="sandbox-runner directory")] = REPO_ROOT
    / "sandbox-runner",
) -> None:
    """Build the safepilot-sandbox image."""
    settings = load_settings()
    client = _docker()
    typer.echo(f"Building {settings.sandbox_image} from {path} ...")
    image, _ = client.images.build(path=str(path), tag=settings.sandbox_image, rm=True)
    typer.secho(f"Built {settings.sandbox_image} ({image.short_id})", fg="green")


@sandbox_app.command("verify")
def sandbox_verify() -> None:
    """Start a throwaway sandbox with the real flags and prove isolation (Section 8.4)."""
    settings = load_settings()
    client = _docker()
    host_has = [k for k in FORBIDDEN_ENV_KEYS if os.environ.get(k)]
    env, attrs = dump_sandbox_env(client, settings)
    problems = isolation_problems(attrs)
    leaked = env_secret_keys(env)
    problems.extend(f"sandbox env contains {k}" for k in leaked)
    typer.echo(f"Sandbox env keys: {', '.join(sorted(env)) or '(none)'}")
    if host_has:
        typer.echo(f"Host process has {', '.join(host_has)} set; sandbox must not inherit them.")
    if problems:
        for problem in problems:
            typer.secho(f"FAIL {problem}", fg="red")
        raise typer.Exit(1)
    typer.secho(
        "PASS isolation flags, read-only rootfs, dropped caps, no secrets in env", fg="green"
    )


@sandbox_app.command("sweep")
def sandbox_sweep() -> None:
    """Remove leftover safepilot sandbox containers."""
    removed = sweep_leftovers(_docker())
    typer.echo(f"Removed {len(removed)} container(s){': ' + ', '.join(removed) if removed else ''}")


def _load_actions(path: Path | None) -> deque[dict[str, Any]]:
    if path is None:
        return deque()
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    return deque(json.loads(ln) for ln in lines)


def _print_event(event: dict[str, Any], as_json: bool) -> None:
    if as_json:
        shown = {k: v for k, v in event.items() if k != "data"}
        typer.echo(json.dumps(shown))
        return
    kind = event.get("type")
    if kind == "step_result":
        mark = "ok " if event.get("ok") else "ERR"
        target = event.get("selector") or ""
        line = f"  step {event['step']:>2} {mark} {event['action']} {target} -> {event['page_url']}"
        typer.secho(line, fg="green" if event.get("ok") else "red")
        if event.get("error"):
            typer.secho(f"           {event['error']}", fg="red")
    elif kind in {"runner_error", "console"}:
        typer.secho(f"  {kind}: {event.get('error') or event.get('message')}", fg="yellow")
    elif kind in {"runner_started", "runner_finished"}:
        typer.echo(f"  {kind} {event.get('reason', '')}")


@sandbox_app.command("run")
def sandbox_run(
    url: Annotated[str, typer.Argument(help="Target URL (http or https).")],
    box: Annotated[str, typer.Option(help="box1, box2, or box3")] = "box1",
    actions: Annotated[
        Path | None, typer.Option(help="JSONL file of actions sent after the initial goto.")
    ] = None,
    timeout: Annotated[int | None, typer.Option(help="Wall-clock seconds.")] = None,
    out: Annotated[Path, typer.Option(help="Where to save screenshots.")] = Path("run-output"),
    as_json: Annotated[bool, typer.Option("--json", help="Print raw events.")] = False,
) -> None:
    """Run one box in a sandbox with scripted actions. No inference involved."""
    # TODO(step 3): replace with the full Section 3.3 / 5.5 URL policy from orch/injection.py.
    if not url.startswith(("http://", "https://")):
        raise typer.BadParameter("only http and https URLs are allowed", param_hint="url")
    if box not in BOXES:
        raise typer.BadParameter(f"choose one of {', '.join(BOXES)}", param_hint="--box")
    settings = load_settings()
    client = _docker()
    queue = _load_actions(actions)
    run_id = uuid.uuid4().hex[:12]
    job = SandboxJob.for_box(run_id, box, url, initial_action={"action": "goto", "url": url})
    out_dir = out / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    typer.echo(f"run {run_id} {box} ({BOXES[box].name}) {url}")

    finished_ok = False
    with SandboxSession(client, job, settings, timeout_seconds=timeout) as session:
        try:
            for event in session.events():
                if event.get("type") == "awaiting_action":
                    session.send(queue.popleft() if queue else {"action": "done"})
                    continue
                if event.get("type") == "screenshot" and event.get("data"):
                    shot = out_dir / Path(event["path"]).name
                    shot.write_bytes(base64.b64decode(event["data"]))
                    event = {**event, "saved_to": str(shot)}
                    if not as_json:
                        typer.echo(f"           screenshot -> {shot}")
                _print_event(event, as_json)
                if event.get("type") == "runner_finished":
                    finished_ok = bool(event.get("ok"))
                    break
        except WallClockExceeded as exc:
            receipt = session.contain("timeout", notes=str(exc))
            typer.secho("Containment Receipt", fg="red", bold=True)
            typer.echo(receipt.model_dump_json(indent=2))
            raise typer.Exit(1) from exc
    destroyed = "destroyed" if session.destroyed else "NOT destroyed"
    typer.echo(f"container {destroyed}")
    raise typer.Exit(0 if finished_ok and session.destroyed else 1)


if __name__ == "__main__":
    app()
