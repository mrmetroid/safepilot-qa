"""Pure helpers for the CLI: event lines, the human approval decision, and exit codes."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

from click.exceptions import Abort

ApprovalMode = Literal["ask", "block"]
QUIET_EVENTS = {"box_stats", "screenshot", "run_verdict"}


def tag(ev: dict[str, Any], names: dict[str, str]) -> str:
    box_id = ev.get("box_id", "")
    name = names.get(box_id, "")
    return f"[{box_id} {name}]" if name else f"[{box_id}]"


def format_event(ev: dict[str, Any], names: dict[str, str]) -> str | None:
    """One human-readable line (or block) per run event. None means: do not print."""
    kind = ev.get("type")
    if kind in QUIET_EVENTS:
        return None
    t = tag(ev, names)
    if kind == "box_started":
        exposed = (ev.get("isolation") or {}).get("secrets_exposed", "?")
        return f"{t} started container {ev.get('container_id')} (secrets exposed: {exposed})"
    if kind == "step_update":
        step = f"step {ev['step']} " if ev.get("step") is not None else ""
        status = "" if ev.get("ok", True) else "  [retry]"
        return f"{t} {step}{ev.get('log') or ev.get('action') or ''}{status}"
    if kind in ("vision_result", "vision_audit"):
        bugs = ev.get("bugs") or []
        lines = [f"{t} vision audit: {len(bugs)} bug(s)"]
        lines += [f"      {b.get('severity', '?'):<8} {b.get('title', '')}" for b in bugs]
        return "\n".join(lines)
    if kind == "approval_required":
        target = " ".join(str(x) for x in (ev.get("action"), ev.get("selector")) if x)
        return f"{t} APPROVAL REQUIRED: {ev.get('reason')} ({target} on {ev.get('page_url')})"
    if kind == "approval_decided":
        return f"{t} approval decision: {ev.get('decision')}"
    if kind == "containment_triggered":
        keys = ("trigger_reason", "signal", "elapsed_ms", "peak_cpu_pct", "peak_mem_mb",
                "secrets_exposed", "host_impact", "container_destroyed")
        body = "\n".join(f"      {k}: {json.dumps(ev.get(k))}" for k in keys)
        return f"{t} Containment Receipt\n{body}\n      notes: {ev.get('notes', '')}"
    if kind == "box_finished":
        return f"{t} finished: {ev.get('status')}. {ev.get('summary') or ''}".rstrip()
    return f"{t} {kind}"


def strip_binary(ev: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in ev.items() if k != "data_base64"}


def approval_prompt(ev: dict[str, Any], names: dict[str, str]) -> str:
    target = " ".join(str(x) for x in (ev.get("action"), ev.get("selector")) if x)
    return f"{tag(ev, names)} wants to {target} on {ev.get('page_url')}. Approve?"


def resolve_approval(
    ev: dict[str, Any], names: dict[str, str], mode: ApprovalMode, ask: Callable[[str], bool]
) -> str:
    """The human gate. Only an explicit yes from a person approves; everything else blocks."""
    if mode == "block":
        return "block"
    try:
        return "approve" if ask(approval_prompt(ev, names)) is True else "block"
    except (Abort, EOFError, KeyboardInterrupt, OSError):
        return "block"  # no answer is not an approval


def verdict_exit_code(verdict: str | None) -> int:
    return {"SHIP IT": 0, "DO NOT SHIP": 1}.get(verdict or "", 2)


def summary_lines(verdict_event: dict[str, Any]) -> list[str]:
    lines = [verdict_event.get("verdict") or "NO VERDICT", verdict_event.get("headline") or ""]
    for r in verdict_event.get("results") or []:
        extra = []
        if r.get("approval"):
            extra.append(f"approval={r['approval']}")
        if r.get("contained"):
            extra.append("contained")
        if r.get("bugs"):
            extra.append(f"bugs={r['bugs']}")
        lines.append(
            f"  {r.get('box_id')} {r.get('name', ''):<22} {r.get('status', ''):<10} "
            f"steps={r.get('steps', 0)} {' '.join(extra)}".rstrip()
        )
    return lines
