"""Supervisor health report (BUILD_SPEC Section 6.1). Shared by GET /api/health and the CLI."""

from __future__ import annotations

import asyncio
from typing import Any

from .config import settings
from .inference import client as inference
from .orch import docker_runner
from .orch import run_manager as rm


async def health_report() -> dict[str, Any]:
    docker_err = await asyncio.to_thread(docker_runner.ping)
    image_ok = True
    if docker_err is None:
        try:
            await asyncio.to_thread(docker_runner.client().images.get, settings.sandbox_image)
        except Exception:  # noqa: BLE001
            image_ok = False
    inf_status, inf_err = await inference.health()
    body: dict[str, Any] = {
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
    return body
