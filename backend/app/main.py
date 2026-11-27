"""SafePilot QA control plane (FastAPI). Routes follow BUILD_SPEC Section 6."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from .config import REPO_ROOT, settings
from .inference import client as inference
from .orch import docker_runner, policy
from .orch import run_manager as rm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("safepilot")

# Self-contained vanilla dashboard served by the control plane. The React app in frontend/
# (Vite build -> frontend/dist) is an alternative UI over the same Section 6 contract.
FRONTEND = Path(__file__).parent / "static" / "dashboard.html"


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        docker_runner.ensure_network()
        n = await asyncio.to_thread(docker_runner.sweep_leftovers)
        if n:
            log.info("startup sweep removed %d leftover sandbox(es)", n)
    except Exception as exc:  # noqa: BLE001
        log.error("docker not ready at startup: %s", exc)
    yield


app = FastAPI(title="SafePilot QA control plane", lifespan=lifespan)


class RunRequest(BaseModel):
    mode: Literal["custom", "adversarial_preset"] = "custom"
    url: str | None = None


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "block"]


@app.get("/api/health")
async def health() -> JSONResponse:
    docker_err = await asyncio.to_thread(docker_runner.ping)
    image_ok = True
    if docker_err is None:
        try:
            await asyncio.to_thread(docker_runner.client().images.get, settings.sandbox_image)
        except Exception:  # noqa: BLE001
            image_ok = False
    inf_status, inf_err = await inference.health()
    body = {
        "ok": docker_err is None and image_ok and inf_status == "ok",
        "control_plane": "ok",
        "docker": "ok" if docker_err is None else "error",
        "inference": inf_status,
        "inference_model": inference.active_model(),
        "sandbox_image": settings.sandbox_image,
        "sandbox_image_present": image_ok,
        "time": rm.now_iso(),
        "containment": {
            "process_isolation": "one container per box, no docker socket, no ports",
            "secret_hygiene": "environment={} (zero host secrets)",
            "caps": f"{settings.sandbox_mem_limit} RAM, {settings.sandbox_nano_cpus / 1e9:g} vCPU, "
                    f"{settings.sandbox_pids_limit} PIDs, {settings.sandbox_timeout}s wall clock, read-only rootfs, cap_drop ALL",
            "lifecycle": "SIGKILL + remove(force) on finish, timeout, OOM, CPU trip or injection",
        },
    }
    errors = {}
    if docker_err:
        errors["docker"] = docker_err
    if not image_ok:
        errors["sandbox_image"] = "image not built"
    if inf_err:
        errors["inference"] = inf_err
    if errors:
        body["errors"] = errors
    return JSONResponse(body)


@app.post("/api/runs", status_code=201)
async def create_run(req: RunRequest) -> dict:
    if req.mode == "custom":
        url = (req.url or "").strip()
        if not url:
            raise HTTPException(400, "url is required for custom mode")
        if "://" not in url:
            url = "https://" + url
        reason = await asyncio.to_thread(policy.validate_public_url, url)
        if reason:
            raise HTTPException(400, f"URL rejected: {reason}")
        req.url = url
    active = sum(1 for r in rm.RUNS.values() if r.status == "running")
    if active >= settings.max_concurrent_runs:
        raise HTTPException(429, f"{active} sweep(s) already running on this VM. Try again in a minute.")
    run = rm.create_run(req.mode, req.url)
    return {
        "run_id": run.run_id,
        "status": run.status,
        "mode": run.mode,
        "url": run.url,
        "boxes": [{"box_id": b.box_id, "name": b.name, "status": b.status} for b in run.boxes.values()],
        "ws_url": f"/ws/runs/{run.run_id}",
    }


@app.get("/api/runs")
async def list_runs() -> list[dict]:
    return [{"run_id": r.run_id, "mode": r.mode, "url": r.url, "status": r.status, "verdict": r.verdict,
             "started_at": r.started_at} for r in reversed(list(rm.RUNS.values()))][:20]


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = rm.RUNS.get(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    snap = run.snapshot()
    snap["inference_model"] = inference.active_model()
    return snap


@app.post("/api/runs/{run_id}/boxes/{box_id}/approve")
async def approve(run_id: str, box_id: str, req: ApprovalRequest) -> dict:
    run = rm.RUNS.get(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if not rm.decide(run, box_id, req.decision):
        raise HTTPException(409, "box is not waiting for approval")
    return {"run_id": run_id, "box_id": box_id, "decision": req.decision, "accepted": True}


@app.get("/api/runs/{run_id}/boxes/{box_id}/screenshots/{step}")
async def screenshot(run_id: str, box_id: str, step: int) -> Response:
    run = rm.RUNS.get(run_id)
    got = rm.screenshot_bytes(run, box_id, step) if run else None
    if not got:
        raise HTTPException(404, "screenshot not found")
    data, ctype = got
    return Response(content=data, media_type=ctype)


@app.websocket("/ws/runs/{run_id}")
async def ws_run(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    run = rm.RUNS.get(run_id)
    if not run:
        await ws.send_json({"type": "error", "error": "run not found"})
        await ws.close()
        return
    q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    run.subscribers.add(q)
    try:
        snap = run.snapshot()
        snap["inference_model"] = inference.active_model()
        await ws.send_json({"type": "snapshot", "run_id": run_id, "run": snap})
        while True:
            ev = await q.get()
            await ws.send_json(ev)
    except WebSocketDisconnect:
        pass
    finally:
        run.subscribers.discard(q)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND)
