"""Pydantic contracts from BUILD_SPEC Sections 3 and 6 (only what is implemented so far)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

BoxId = Literal["box1", "box2", "box3"]
Persona = Literal["happy_path", "mobile_vision", "chaos_gremlin"]
TriggerReason = Literal["cpu_limit_exceeded", "timeout", "prompt_injection_detected", "oom_killed"]


@dataclass(frozen=True)
class BoxSpec:
    box_id: BoxId
    name: str
    persona: Persona
    width: int
    height: int


# Appendix A.
BOXES: dict[str, BoxSpec] = {
    "box1": BoxSpec("box1", "Happy Path", "happy_path", 1280, 800),
    "box2": BoxSpec("box2", "Mobile Vision Check", "mobile_vision", 390, 844),
    "box3": BoxSpec("box3", "Chaos Gremlin", "chaos_gremlin", 1280, 800),
}


class Viewport(BaseModel):
    width: int
    height: int


class SandboxJob(BaseModel):
    """Section 3.4. Never carries model names, keys, or host tokens."""

    run_id: str
    box_id: BoxId
    box_name: str
    target_url: str
    persona: Persona
    viewport: Viewport
    max_steps: int = 16
    step_timeout_seconds: int = 8
    allowed_actions: list[str] = [
        "goto",
        "click",
        "fill",
        "press",
        "hover",
        "scroll",
        "wait",
        "assert_text",
        "screenshot",
        "done",
    ]
    initial_action: dict | None = None

    @classmethod
    def for_box(cls, run_id: str, box_id: str, target_url: str, **overrides) -> SandboxJob:
        spec = BOXES[box_id]
        return cls(
            run_id=run_id,
            box_id=spec.box_id,
            box_name=spec.name,
            target_url=target_url,
            persona=spec.persona,
            viewport=Viewport(width=spec.width, height=spec.height),
            **overrides,
        )


class ContainmentReceipt(BaseModel):
    """Section 3.6. Field names and enums are required by the spec."""

    container_id: str
    box_name: str
    box_id: BoxId
    run_id: str
    trigger_reason: TriggerReason
    signal: Literal["SIGKILL"] = "SIGKILL"
    elapsed_ms: int
    peak_cpu_pct: float
    peak_mem_mb: float
    secrets_exposed: int = 0
    host_impact: str = "none"
    container_destroyed: bool
    timestamp_iso: str
    notes: str | None = None
