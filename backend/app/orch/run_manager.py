"""Run orchestration: the 3-box swarm, watchdog, approval gate, containment and verdict."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..config import settings
from ..inference import agents
from . import docker_runner, policy
from .docker_runner import Sandbox

log = logging.getLogger("safepilot.runs")

# Run settings (additive to BUILD_SPEC Section 6.2). Container caps are NOT configurable:
# RAM, swap, vCPU, PIDs, read-only rootfs and dropped caps always come from config.Settings.
DEVICES: dict[str, dict[str, int]] = {
    "desktop": {"width": 1280, "height": 800},
    "tablet": {"width": 820, "height": 1180},
    "mobile": {"width": 390, "height": 844},
}
PERSONA_INFO = {
    # persona: (display name, default device)
    "happy_path": ("Happy Path", "desktop"),  # demo preset only
    "mobile_vision": ("Vision Check", "mobile"),
    "chaos_gremlin": ("Chaos Gremlin", "desktop"),
}
MAX_AGENTS_PER_RUN = 6


@dataclass(frozen=True)
class RunConfig:
    agents: tuple[tuple[str, str], ...]  # (persona, device)
    model: str | None = None
    max_steps: int = settings.max_steps
    timeout_seconds: int = settings.sandbox_timeout
    focus: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "agents": [{"persona": p, "device": d, "viewport": DEVICES[d]} for p, d in self.agents],
            "model": self.model or settings.inference_model,
            "max_steps": self.max_steps,
            "timeout_seconds": self.timeout_seconds,
            "focus": self.focus,
            "approval_gate": ("Happy Path pauses for a human Approve before irreversible actions"
                              if any(p == "happy_path" for p, _ in self.agents)
                              else "irreversible actions are refused, never executed"),
            "caps": {"mem_limit": settings.sandbox_mem_limit, "nano_cpus": settings.sandbox_nano_cpus,
                     "pids_limit": settings.sandbox_pids_limit, "read_only": True, "cap_drop": ["ALL"]},
        }


# Demo preset only: the fixed 3-box swarm from BUILD_SPEC Section 5 (Happy Path with the Approve gate).
DEMO_CONFIG = RunConfig(agents=(("happy_path", "desktop"), ("mobile_vision", "mobile"), ("chaos_gremlin", "desktop")))
# Default for custom URLs: no Happy Path. Irreversible actions are refused, never executed.
DEFAULT_CONFIG = RunConfig(agents=(("mobile_vision", "mobile"), ("mobile_vision", "desktop"), ("chaos_gremlin", "desktop")))
USER_PERSONAS = ("mobile_vision", "chaos_gremlin")


def plan_boxes(cfg: RunConfig) -> list[tuple[str, str, str, dict[str, int]]]:
    """Sequential box ids (box1..N) in agent order, with readable, de-duplicated names."""
    out: list[tuple[str, str, str, dict[str, int]]] = []
    counts: dict[str, int] = {}
    for i, (persona, device) in enumerate(cfg.agents, start=1):
        name, default_dev = PERSONA_INFO[persona]
        label = name if device == default_dev else f"{name} ({device.capitalize()})"
        if persona == "mobile_vision" and device == "mobile":
            label = "Mobile Vision Check"
        counts[label] = counts.get(label, 0) + 1
        if counts[label] > 1:
            label += f" #{counts[label]}"
        out.append((f"box{i}", label, persona, dict(DEVICES[device])))
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Containment(Exception):
    def __init__(self, reason: str, notes: str, signal_at: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.notes = notes
        self.signal_at = signal_at or time.monotonic()


class BoxFailed(Exception):
    pass


@dataclass
class BoxState:
    box_id: str
    name: str
    persona: str
    viewport: dict[str, int]
    status: str = "starting"
    retry_count: int = 0
    steps: list[dict[str, Any]] = field(default_factory=list)
    screenshots: list[dict[str, Any]] = field(default_factory=list)
    approval: dict[str, Any] = field(default_factory=lambda: {"required": False, "decision": None, "reason": None})
    containment_receipt: dict[str, Any] | None = None
    summary: str | None = None
    bugs: list[dict[str, Any]] = field(default_factory=list)
    vision_summary: str | None = None
    annotated_step: int | None = None
    container_id: str | None = None
    isolation: dict[str, Any] = field(default_factory=dict)
    cpu_pct: float = 0.0
    mem_mb: float = 0.0
    # timing (monotonic)
    active_started: float = 0.0
    paused_total: float = 0.0
    paused_since: float | None = None
    approval_future: asyncio.Future | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "box_id": self.box_id,
            "name": self.name,
            "persona": self.persona,
            "viewport": self.viewport,
            "status": self.status,
            "retry_count": self.retry_count,
            "steps": self.steps,
            "screenshots": [{k: v for k, v in s.items() if k != "data_base64"} for s in self.screenshots],
            "approval": self.approval,
            "containment_receipt": self.containment_receipt,
            "summary": self.summary,
            "bugs": self.bugs,
            "vision_summary": self.vision_summary,
            "annotated_step": self.annotated_step,
            "container_id": self.container_id,
            "isolation": self.isolation,
            "cpu_pct": self.cpu_pct,
            "mem_mb": self.mem_mb,
        }

    def active_elapsed(self) -> float:
        if not self.active_started:
            return 0.0
        paused = self.paused_total + ((time.monotonic() - self.paused_since) if self.paused_since else 0.0)
        return time.monotonic() - self.active_started - paused


@dataclass
class Run:
    run_id: str
    mode: str
    url: str  # what the human sees
    target_url: str  # what the sandboxes open
    approved_host: str
    status: str = "running"
    started_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    verdict: str | None = None
    headline: str | None = None
    fix_prompt: str | None = None
    fix_prompt_source: str | None = None
    boxes: dict[str, BoxState] = field(default_factory=dict)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    log: list[dict[str, Any]] = field(default_factory=list)
    cfg: RunConfig = DEFAULT_CONFIG
    annotated_box_id: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "mode": self.mode,
            "url": self.url,
            "target_url": self.target_url,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "verdict": self.verdict,
            "headline": self.headline,
            "fix_prompt": self.fix_prompt,
            "fix_prompt_source": self.fix_prompt_source,
            "inference_model": None,
            "settings": self.cfg.public(),
            "annotated_screenshot_box_id": self.annotated_box_id,
            "boxes": {k: b.snapshot() for k, b in self.boxes.items()},
        }

    def emit(self, event_type: str, **fields: Any) -> dict[str, Any]:
        ev = {"type": event_type, "run_id": self.run_id, "ts": now_iso(), **fields}
        if event_type != "screenshot":
            self.log.append(ev)
        for q in list(self.subscribers):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                pass
        return ev


RUNS: dict[str, Run] = {}


# =========================================================================== public API
def active_sandboxes() -> int:
    return sum(1 for r in RUNS.values() for b in r.boxes.values()
               if b.status in ("starting", "running", "waiting_for_approval"))


def create_run(mode: str, url: str | None, cfg: RunConfig | None = None) -> Run:
    run_id = str(uuid.uuid4())
    cfg = cfg or (DEMO_CONFIG if mode == "adversarial_preset" else DEFAULT_CONFIG)
    if mode == "adversarial_preset":
        run = Run(run_id, mode, settings.demo_target_public_url, settings.demo_target_sandbox_url, settings.demo_target_host)
    else:
        assert url
        run = Run(run_id, mode, url, url, approved_host="__none__")
    run.cfg = cfg
    for box_id, name, persona, vp in plan_boxes(cfg):
        run.boxes[box_id] = BoxState(box_id, name, persona, vp)
    RUNS[run_id] = run
    asyncio.get_running_loop().create_task(_run_all(run))
    return run


def decide(run: Run, box_id: str, decision: str) -> bool:
    box = run.boxes.get(box_id)
    if not box or box.status != "waiting_for_approval" or not box.approval_future or box.approval_future.done():
        return False
    box.approval_future.set_result(decision)
    return True


# =========================================================================== orchestration
async def _run_all(run: Run) -> None:
    await asyncio.gather(*(_supervise_box(run, b) for b in run.boxes.values()), return_exceptions=True)
    await _finalize(run)


async def _supervise_box(run: Run, box: BoxState) -> None:
    loop = asyncio.get_running_loop()
    sb = Sandbox(run.run_id, box.box_id, loop)
    job = {
        "run_id": run.run_id,
        "box_id": box.box_id,
        "box_name": box.name,
        "target_url": run.target_url,
        "persona": box.persona,
        "viewport": box.viewport,
        "max_steps": run.cfg.max_steps,
        "step_timeout_seconds": settings.step_timeout,
        "allowed_actions": ["goto", "click", "fill", "press", "hover", "scroll", "wait", "assert_text", "screenshot", "done"],
        "initial_action": None,
    }
    try:
        await asyncio.to_thread(sb.start, job)
    except Exception as exc:  # noqa: BLE001
        box.status = "failed"
        box.summary = f"Could not start sandbox: {str(exc)[:200]}"
        run.emit("box_finished", box_id=box.box_id, status="failed", summary=box.summary)
        return
    box.container_id = sb.short_id
    box.active_started = time.monotonic()
    box.isolation = await asyncio.to_thread(sb.inspect_env)
    box.status = "running"
    run.emit("box_started", box_id=box.box_id, container_id=sb.short_id, name=box.name, isolation=box.isolation)

    main = asyncio.create_task(_box_logic(run, box, sb))
    dog = asyncio.create_task(_watchdog(run, box, sb, main))
    try:
        await main
        status = box.status if box.status in ("completed", "blocked", "failed") else "completed"
        box.status = status
        sb.send({"action": "exit", "reason": status})
        await asyncio.sleep(0.2)
        await asyncio.to_thread(sb.destroy)
        run.emit("box_finished", box_id=box.box_id, status=status, summary=box.summary)
    except Containment as c:
        await _contain(run, box, sb, c)
    except asyncio.CancelledError:
        c = getattr(main, "_containment", None)
        if c is None:
            c = Containment("timeout", "Run cancelled")
        await _contain(run, box, sb, c)
    except BoxFailed as exc:
        box.status = "failed"
        box.summary = str(exc)
        await asyncio.to_thread(sb.destroy)
        run.emit("box_finished", box_id=box.box_id, status="failed", summary=box.summary)
    except Exception as exc:  # noqa: BLE001
        log.exception("box %s crashed", box.box_id)
        box.status = "failed"
        box.summary = f"Control-plane error: {str(exc)[:200]}"
        await asyncio.to_thread(sb.destroy)
        run.emit("box_finished", box_id=box.box_id, status="failed", summary=box.summary)
    finally:
        dog.cancel()
        if not sb.destroyed:
            await asyncio.to_thread(sb.destroy)


async def _watchdog(run: Run, box: BoxState, sb: Sandbox, main: asyncio.Task) -> None:
    """Trusted supervisor: wall clock, sustained CPU, OOM. Cancels the box logic on a trip."""
    last_emit = 0.0
    while not main.done():
        await asyncio.sleep(0.25)
        st = sb.stats
        box.cpu_pct, box.mem_mb = st.cpu_pct, st.mem_mb
        if time.monotonic() - last_emit > 1.0:
            last_emit = time.monotonic()
            run.emit("box_stats", box_id=box.box_id, cpu_pct=st.cpu_pct, mem_mb=st.mem_mb, pids=st.pids,
                     elapsed_s=round(box.active_elapsed(), 1), status=box.status)
        reason = None
        if box.paused_since is None and box.active_elapsed() > run.cfg.timeout_seconds:
            reason = Containment("timeout", f"Exceeded the {run.cfg.timeout_seconds}s wall-clock cap")
        elif getattr(box, "_armed", False) and st.hot_since and time.monotonic() - st.hot_since >= settings.cpu_trip_seconds \
                and box.paused_since is None:
            reason = Containment("cpu_limit_exceeded",
                                 f"Sustained {st.cpu_pct:.0f}% of its 1 vCPU quota for {settings.cpu_trip_seconds}s",
                                 signal_at=st.hot_since)
        elif sb.exited and not main.done():
            if await asyncio.to_thread(sb.oom_killed):
                reason = Containment("oom_killed", "Kernel OOM-killed the sandbox at its 512 MiB cap")
        if reason:
            main._containment = reason  # type: ignore[attr-defined]
            main.cancel()
            return


async def _next_obs(sb: Sandbox, timeout: float) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Wait for one step_result and its screenshot."""
    deadline = time.monotonic() + timeout
    obs: dict[str, Any] | None = None
    shot: dict[str, Any] | None = None
    while True:
        remaining = deadline - time.monotonic()
        if obs is not None:
            remaining = min(remaining, 4.0)
        if remaining <= 0:
            if obs is not None:
                return obs, shot
            raise Containment("timeout", "Sandbox stopped responding (page hung the browser)")
        try:
            ev = await asyncio.wait_for(sb.events.get(), timeout=remaining)
        except asyncio.TimeoutError:
            continue
        t = ev.get("type")
        if t == "step_result":
            if obs is not None:
                return obs, shot
            obs = ev
            obs["_received"] = time.monotonic()
        elif t == "screenshot" and obs is not None and ev.get("step") == obs.get("step"):
            return obs, ev
        elif t == "runner_error":
            raise BoxFailed(f"Runner error: {ev.get('error')}")
        elif t == "_container_exited":
            if sb.oom_killed():
                raise Containment("oom_killed", "Kernel OOM-killed the sandbox at its 512 MiB cap")
            if obs is not None:
                return obs, shot
            raise BoxFailed("Sandbox exited unexpectedly")


def _record(run: Run, box: BoxState, obs: dict[str, Any], shot: dict[str, Any] | None, planned: dict[str, Any] | None) -> None:
    step = obs.get("step", 0)
    entry = {
        "step": step,
        "action": obs.get("action"),
        "selector": obs.get("selector"),
        "value": (planned or {}).get("value"),
        "url": (planned or {}).get("url"),
        "ok": obs.get("ok"),
        "error": obs.get("error"),
        "thought": (planned or {}).get("thought") or ("Open target" if step == 0 else ""),
        "source": (planned or {}).get("source"),
        "page_url": obs.get("page_url"),
        "title": obs.get("title"),
        "console_errors": obs.get("console_errors") or [],
    }
    box.steps.append(entry)
    if obs.get("ok") is False:
        box.retry_count += 1
    verb = entry["action"] or "observe"
    target = entry["selector"] or entry["url"] or entry["page_url"] or ""
    log_line = f"{verb} {target}".strip() + ("" if entry["ok"] else f"  FAILED: {str(entry['error'])[:80]}")
    run.emit("step_update", box_id=box.box_id, step=step, thought=entry["thought"], action=entry["action"],
             selector=entry["selector"], ok=entry["ok"], retry_count=box.retry_count, page_url=entry["page_url"],
             cpu_pct=box.cpu_pct, mem_mb=box.mem_mb, log=log_line, source=entry["source"],
             console_errors=entry["console_errors"][:3])
    if shot and shot.get("data"):
        rec = {"step": step, "content_type": shot.get("content_type", "image/jpeg"), "data_base64": shot["data"],
               "width": shot.get("width"), "height": shot.get("height")}
        box.screenshots.append(rec)
        box.screenshots = box.screenshots[-24:]
        run.emit("screenshot", box_id=box.box_id, step=step, content_type=rec["content_type"],
                 data_base64=rec["data_base64"], width=rec["width"], height=rec["height"])


def _scan_obs(obs: dict[str, Any]) -> str | None:
    return policy.scan_text(obs.get("extracted_text"), obs.get("hidden_text"), " ".join(obs.get("console_errors") or []))


async def _box_logic(run: Run, box: BoxState, sb: Sandbox) -> None:
    step_budget = settings.step_timeout * 3 + 15
    history: list[dict[str, Any]] = []
    obs, shot = await _next_obs(sb, timeout=step_budget + 20)  # first load includes Chromium startup
    planned: dict[str, Any] | None = None
    audits = 0
    audited_urls: set[str] = set()

    while True:
        _record(run, box, obs, shot, planned)
        box._armed = True  # type: ignore[attr-defined]  # CPU trip only after first page load
        history.append(box.steps[-1])

        hit = _scan_obs(obs)
        if hit:
            raise Containment("prompt_injection_detected", f"Page content: {hit}", signal_at=obs.get("_received"))

        if box.persona == "mobile_vision" and audits < 2 and obs.get("page_url") not in audited_urls and shot:
            audits += 1
            audited_urls.add(obs.get("page_url"))
            run.emit("step_update", box_id=box.box_id, step=obs.get("step"), log="Vision audit on Vultr Serverless Inference...",
                     action="vision_audit", ok=True, retry_count=box.retry_count, cpu_pct=box.cpu_pct, mem_mb=box.mem_mb)
            audit = await agents.audit_mobile(obs, shot.get("data"), box.viewport, run.cfg.model)
            sev = lambda bugs: sum(3 if b.get("severity") == "critical" else 2 if b.get("severity") == "major" else 1 for b in bugs)  # noqa: E731
            if not box.bugs or sev(audit["bugs"]) > sev(box.bugs):
                box.bugs = audit["bugs"]
                box.annotated_step = obs.get("step")
                box.vision_summary = audit["summary"]
            run.emit("vision_result", box_id=box.box_id, step=obs.get("step"), bugs=audit["bugs"],
                     summary=audit["summary"], source=audit["source"])
            # Same payload under the name the React dashboard (frontend/) listens for.
            run.emit("vision_audit", box_id=box.box_id, step=obs.get("step"), bugs=audit["bugs"],
                     summary=audit["summary"], source=audit["source"])

        step = len(history)
        if step > run.cfg.max_steps or (box.persona == "mobile_vision" and step > 4):
            box.status = "completed"
            box.summary = _summary(box, "Step budget used")
            return

        planned = await agents.plan(box.persona, obs, shot.get("data") if shot else None, history,
                                    run.target_url, step, run.cfg.max_steps, model=run.cfg.model,
                                    focus=run.cfg.focus, viewport=box.viewport)
        if planned.get("source") == "heuristic-after-error":
            box.retry_count += 1
        action = {k: planned.get(k) for k in ("action", "selector", "value", "url")}

        blocked = policy.scan_action(planned, run.approved_host, run.target_url)
        if blocked and blocked[0] == "injection":
            raise Containment("prompt_injection_detected", f"Refused model action: {blocked[1]}")

        if planned.get("action") == "done" or planned.get("done") is True:
            box.status = "completed"
            box.summary = _summary(box, planned.get("thought") or "Planner finished")
            return

        gate = policy.is_irreversible(planned, obs.get("dom_summary") or [], obs.get("page_url") or "")
        if gate:
            if box.persona != "happy_path":
                # Only happy-path agents have a human gate. Others are simply refused.
                obs = {**obs, "step": step, "action": action["action"], "selector": action["selector"], "ok": False,
                       "error": f"Refused by policy: {gate} (no approval gate for this persona)"}
                shot = None
                continue
            if planned.get("action") == "hold_for_approval" or not action.get("selector"):
                btn = next((el for el in obs.get("dom_summary") or [] if policy.IRREVERSIBLE_TEXT.search(el.get("text") or "")
                            or policy.IRREVERSIBLE_SELECTOR.search(el.get("sel") or "")), None)
                if not btn:
                    box.status = "failed"
                    box.summary = "Planner asked for approval but no submit control was found."
                    return
                action = {"action": "click", "selector": btn["sel"], "value": None, "url": None}
            decision = await _await_approval(run, box, action, obs, gate)
            if decision != "approve":
                box.status = "blocked"
                box.summary = f"Human blocked the irreversible action ({gate}). Flow reached checkout but was not submitted."
                return
            sb.send(action)
            obs, shot = await _next_obs(sb, timeout=step_budget)
            planned = {**planned, **action, "thought": "Human approved: submitting"}
            _record(run, box, obs, shot, planned)
            box.status = "completed" if obs.get("ok") else "failed"
            box.summary = (f"Reached checkout and submitted after human Approve. Final page: {obs.get('title') or obs.get('page_url')}"
                           if obs.get("ok") else f"Approved submit failed: {obs.get('error')}")
            return

        if blocked and blocked[0] == "off_origin":
            obs = {**obs, "step": step, "action": action["action"], "selector": action["url"], "ok": False, "error": blocked[1]}
            shot = None
            continue

        sb.send(action)
        obs, shot = await _next_obs(sb, timeout=step_budget)


async def _await_approval(run: Run, box: BoxState, action: dict[str, Any], obs: dict[str, Any], reason: str) -> str:
    loop = asyncio.get_running_loop()
    box.approval_future = loop.create_future()
    box.status = "waiting_for_approval"
    box.paused_since = time.monotonic()  # wall-clock cap pauses while a human decides
    box.approval = {"required": True, "decision": None, "reason": reason, "action": action, "page_url": obs.get("page_url")}
    run.emit("approval_required", box_id=box.box_id, action=action["action"], selector=action.get("selector"),
             page_url=obs.get("page_url"), reason=reason)
    try:
        decision = await asyncio.wait_for(box.approval_future, timeout=settings.run_timeout)
    except asyncio.TimeoutError:
        decision = "block"  # never auto-approve
    box.paused_total += time.monotonic() - box.paused_since
    box.paused_since = None
    box.approval["decision"] = decision
    box.status = "running"
    run.emit("approval_decided", box_id=box.box_id, decision=decision)
    return decision


def _summary(box: BoxState, tail: str) -> str:
    if box.persona == "happy_path":
        last = box.steps[-1] if box.steps else {}
        return f"Did not reach an approved submit. Last page: {last.get('page_url')}. {tail}"
    if box.persona == "mobile_vision":
        n = len([b for b in box.bugs if b.get("severity") in ("critical", "major")])
        return f"{len(box.bugs)} visual bug(s), {n} critical/major. {box.vision_summary or ''}".strip()
    return f"Explored {len(box.steps)} step(s) without tripping a containment policy. {tail}"


async def _contain(run: Run, box: BoxState, sb: Sandbox, c: Containment) -> None:
    peak_cpu, peak_mem = sb.stats.peak_cpu_pct, sb.stats.peak_mem_mb
    destroyed = await asyncio.to_thread(sb.destroy)
    elapsed_ms = int((time.monotonic() - c.signal_at) * 1000)
    docker_ok = docker_runner.ping() is None
    receipt = {
        "container_id": sb.short_id,
        "box_name": box.name,
        "box_id": box.box_id,
        "run_id": run.run_id,
        "trigger_reason": c.reason,
        "signal": "SIGKILL",
        "elapsed_ms": elapsed_ms,
        "peak_cpu_pct": round(peak_cpu, 1),
        "peak_mem_mb": round(peak_mem, 1),
        "secrets_exposed": int(box.isolation.get("secrets_exposed", 0)),
        "host_impact": "none" if docker_ok else "degraded",
        "container_destroyed": destroyed,
        "timestamp_iso": now_iso(),
        "notes": c.notes[:500],
    }
    box.containment_receipt = receipt
    box.status = "contained"
    box.summary = f"Contained: {c.reason}. {c.notes[:200]}"
    run.emit("containment_triggered", box_id=box.box_id, **{k: v for k, v in receipt.items() if k not in ("run_id", "box_id")})
    run.emit("box_finished", box_id=box.box_id, status="contained", summary=box.summary)


def _sev_score(bugs: list[dict[str, Any]]) -> int:
    return sum(3 if b.get("severity") == "critical" else 2 if b.get("severity") == "major" else 1 for b in bugs)


async def _finalize(run: Run) -> None:
    by = lambda p: [b for b in run.boxes.values() if b.persona == p]  # noqa: E731
    happy, vision, chaos = by("happy_path"), by("mobile_vision"), by("chaos_gremlin")
    reasons: list[str] = []

    all_bugs: list[dict[str, Any]] = []
    for b in vision:
        for bug in b.bugs:
            all_bugs.append({**bug, "box_id": b.box_id, "viewport": f"{b.viewport['width']}x{b.viewport['height']}"})
    best = max((b for b in vision if b.bugs), key=lambda b: _sev_score(b.bugs), default=None)
    run.annotated_box_id = best.box_id if best else (vision[0].box_id if vision else None)

    serious = sorted((b for b in all_bugs if b.get("severity") in ("critical", "major")),
                     key=lambda b: b.get("severity") != "critical")
    if serious:
        top = serious[0]
        what = re.sub(r"\s+", " ", f"{top.get('title', 'Layout bug')}")
        reasons.append(f"{top['viewport']} ({top.get('severity')}): {what}")
    for b in happy:
        who = "happy path" if len(happy) == 1 else f"{b.name}"
        if b.status == "completed" and b.approval.get("decision") is None:
            reasons.append(f"{who} never reached an approvable checkout")
        elif b.status != "completed":
            reasons.append(f"{who} was blocked" if b.status == "blocked" else f"{who} did not complete")
    seen: set[str] = set()
    for b in chaos:
        if b.status == "contained" and b.containment_receipt:
            r = b.containment_receipt["trigger_reason"]
            txt = {"prompt_injection_detected": "the site serves a prompt-injection payload",
                   "cpu_limit_exceeded": "the site locks up the CPU",
                   "oom_killed": "the site exhausts memory",
                   "timeout": "the site hangs the browser"}.get(r, r)
            if txt not in seen:
                seen.add(txt)
                reasons.append(txt)
    for b in vision:
        if b.status == "failed":
            reasons.append(f"{b.name} could not run")
    for b in happy + vision:
        if b.status == "contained" and b.containment_receipt:
            reasons.append(f"{b.name} was contained ({b.containment_receipt['trigger_reason']})")

    verdict = "DO NOT SHIP" if reasons else "SHIP IT"
    run.verdict = verdict
    ran = ", ".join(sorted({b.name for b in run.boxes.values()}))
    run.headline = ("; ".join(reasons).capitalize() + ".") if reasons else f"All agents passed ({ran})."

    happy_text = " | ".join(f"{b.name}: {b.status}: {b.summary} (approval decision: {b.approval.get('decision')})"
                            for b in happy) or "not run"
    chaos_text = " | ".join(json_receipt(b) if b.containment_receipt else f"{b.name}: {b.status}: {b.summary}"
                            for b in chaos) or "not run"
    log_box = run.annotated_box_id or next(iter(run.boxes))
    run.emit("step_update", box_id=log_box, log="Generating Cursor fix prompt on Vultr Serverless Inference...",
             action="fix_prompt", ok=True)
    fp = await agents.fix_prompt(run.url, verdict, happy_text, all_bugs, chaos_text, model=run.cfg.model)
    run.fix_prompt = fp.get("fix_prompt")
    run.fix_prompt_source = fp.get("source")
    run.status = "completed"
    run.finished_at = now_iso()
    ann = run.boxes.get(run.annotated_box_id) if run.annotated_box_id else None
    run.emit("run_verdict", verdict=verdict, headline=run.headline, fix_prompt=run.fix_prompt,
             annotated_screenshot_box_id=run.annotated_box_id,
             annotated_screenshot_step=ann.annotated_step if ann else None,
             bugs=ann.bugs if ann else [], all_bugs=all_bugs, fix_prompt_source=run.fix_prompt_source,
             results=[{"box_id": b.box_id, "name": b.name, "persona": b.persona, "viewport": b.viewport,
                       "status": b.status, "summary": b.summary, "steps": len(b.steps), "retries": b.retry_count,
                       "bugs": len(b.bugs), "approval": b.approval.get("decision"),
                       "contained": bool(b.containment_receipt)} for b in run.boxes.values()])


def json_receipt(box: BoxState) -> str:
    r = box.containment_receipt or {}
    return (f"Contained by Canary Swarm ({r.get('trigger_reason')}) after {r.get('elapsed_ms')} ms, peak CPU {r.get('peak_cpu_pct')}%, "
            f"peak mem {r.get('peak_mem_mb')} MB. Notes: {r.get('notes')}")


def screenshot_bytes(run: Run, box_id: str, step: int) -> tuple[bytes, str] | None:
    box = run.boxes.get(box_id)
    if not box:
        return None
    for s in reversed(box.screenshots):
        if s["step"] == step:
            return base64.b64decode(s["data_base64"]), s["content_type"]
    return None
