"""SafePilot QA sandbox runner.

Runs inside an ephemeral `safepilot-sandbox` container. It is an untrusted worker:
it holds no API keys, never calls inference, and never decides on its own to click an
irreversible submit. The control plane supervises it action by action.

Protocol (BUILD_SPEC Section 3.4 / 3.5):

- Input: `runner.py <job.json>` or `runner.py -`. With `-`, the first stdin line is the
  job JSON. After that, every stdin line is one action object, for example
  `{"action": "click", "selector": "#add-to-cart"}`. `done` or EOF ends the run.
- Output: one JSON event per stdout line, each with `type`, `run_id`, `box_id`, `ts`.
  Additive event type `awaiting_action` tells the supervisor the runner is idle.

Runs on the image's Python 3.10, so keep syntax 3.10-compatible.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

DEFAULT_ALLOWED_ACTIONS = [
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
REQUIRED_JOB_FIELDS = ["run_id", "box_id", "target_url", "persona", "viewport"]
SCREENSHOT_DIR = Path("/tmp/screenshots")
TEXT_LIMIT = 2000
DOM_LIMIT = 2500

# Collects interactive elements with a usable selector for the planner.
DOM_SUMMARY_JS = """
() => {
  const out = [];
  const els = document.querySelectorAll(
    'a, button, input, select, textarea, summary, [role=button], [data-testid]');
  for (const el of els) {
    if (out.length >= 60) break;
    let sel = el.tagName.toLowerCase();
    if (el.id) sel = '#' + el.id;
    else if (el.dataset && el.dataset.testid) sel = `[data-testid="${el.dataset.testid}"]`;
    else if (el.name) sel = `${sel}[name="${el.name}"]`;
    const label = (el.innerText || el.value || el.placeholder ||
                   el.getAttribute('aria-label') || '').trim().slice(0, 60);
    const type = el.type ? ` type=${el.type}` : '';
    out.push(`${el.tagName.toLowerCase()}${type} ${sel} "${label}"`);
  }
  return out.join('\\n');
}
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_event(event_type: str, job: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {
        "type": event_type,
        "run_id": job.get("run_id"),
        "box_id": job.get("box_id"),
        "ts": now_iso(),
        **fields,
    }


def validate_job(job: Any) -> dict[str, Any]:
    if not isinstance(job, dict):
        raise ValueError("job must be a JSON object")
    missing = [f for f in REQUIRED_JOB_FIELDS if f not in job]
    if missing:
        raise ValueError(f"job missing fields: {', '.join(missing)}")
    viewport = job["viewport"]
    if not (isinstance(viewport, dict) and {"width", "height"} <= viewport.keys()):
        raise ValueError("viewport must have width and height")
    job.setdefault("max_steps", 16)
    job.setdefault("step_timeout_seconds", 8)
    job.setdefault("allowed_actions", list(DEFAULT_ALLOWED_ACTIONS))
    job.setdefault("initial_action", None)
    return job


def parse_action(raw: str | dict[str, Any], allowed: list[str]) -> dict[str, Any]:
    """Parse and validate one action. Raises ValueError on anything not allowed."""
    action = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(action, dict):
        raise ValueError("action must be a JSON object")
    name = action.get("action")
    if name not in allowed:
        raise ValueError(f"action not allowed: {name!r}")
    if name in {"click", "fill", "hover", "assert_text"} and not action.get("selector"):
        if not (name == "assert_text" and action.get("value")):
            raise ValueError(f"{name} requires a selector")
    if name == "goto":
        url = action.get("url") or ""
        if not url.startswith(("http://", "https://")):
            raise ValueError("goto requires an http(s) url")
    if name == "press" and not action.get("value"):
        raise ValueError("press requires a key in value")
    return action


class Runner:
    def __init__(self, job: dict[str, Any], out: TextIO = sys.stdout) -> None:
        self.job = job
        self.out = out
        self.step = 0
        self.console_errors: list[str] = []
        self.page: Any = None

    def emit(self, event_type: str, **fields: Any) -> None:
        self.out.write(json.dumps(make_event(event_type, self.job, **fields)) + "\n")
        self.out.flush()

    def _on_console(self, msg: Any) -> None:
        if msg.type in {"error", "warning"}:
            text = msg.text[:500]
            if msg.type == "error":
                self.console_errors.append(text)
            self.emit("console", level=msg.type, message=text)

    def _page_state(self) -> dict[str, Any]:
        page = self.page
        try:
            text = page.inner_text("body", timeout=2000)[:TEXT_LIMIT]
        except Exception as exc:  # page may be busy or blank
            text = f"<unavailable: {type(exc).__name__}>"
        try:
            dom = page.evaluate(DOM_SUMMARY_JS)[:DOM_LIMIT]
        except Exception as exc:
            dom = f"<unavailable: {type(exc).__name__}>"
        return {"page_url": page.url, "dom_summary": dom, "extracted_text": text}

    def _screenshot(self) -> None:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        box = self.job["box_id"]
        path = SCREENSHOT_DIR / f"{box}-step-{self.step}.jpg"
        data = self.page.screenshot(path=str(path), type="jpeg", quality=60, timeout=5000)
        vp = self.job["viewport"]
        self.emit(
            "screenshot",
            step=self.step,
            path=str(path),
            width=vp["width"],
            height=vp["height"],
            encoding="base64",
            mime="image/jpeg",
            data=base64.b64encode(data).decode("ascii"),
        )

    def execute(self, action: dict[str, Any]) -> None:
        name = action["action"]
        page = self.page
        selector = action.get("selector")
        value = action.get("value")
        if name == "goto":
            page.goto(action["url"], wait_until="domcontentloaded")
        elif name == "click":
            page.click(selector)
        elif name == "fill":
            page.fill(selector, value or "")
        elif name == "press":
            if selector:
                page.press(selector, value)
            else:
                page.keyboard.press(value)
        elif name == "hover":
            page.hover(selector)
        elif name == "scroll":
            page.mouse.wheel(0, int(value or 600))
        elif name == "wait":
            page.wait_for_timeout(min(float(value or 1), 5) * 1000)
        elif name == "assert_text":
            target = page.locator(selector) if selector else page.locator("body")
            if value and value not in target.inner_text():
                raise AssertionError(f"text not found: {value!r}")
        # "screenshot" needs no browser action; every step ends with one.

    def run_step(self, action: dict[str, Any]) -> None:
        self.step += 1
        self.console_errors = []
        ok, error = True, None
        try:
            self.execute(action)
        except Exception as exc:
            ok, error = False, f"{type(exc).__name__}: {str(exc)[:300]}"
        self.emit(
            "step_result",
            step=self.step,
            action=action["action"],
            selector=action.get("selector"),
            ok=ok,
            error=error,
            console_errors=self.console_errors,
            **self._page_state(),
        )
        try:
            self._screenshot()
        except Exception as exc:
            self.emit("runner_error", error=f"screenshot failed: {type(exc).__name__}: {exc}")

    def run(self, actions: Callable[[], str | None]) -> int:
        from playwright.sync_api import sync_playwright  # only available in the image

        vp = self.job["viewport"]
        self.emit("runner_started", pid=os.getpid(), viewport=vp)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                args=["--disable-dev-shm-usage", "--disable-gpu", "--no-first-run"]
            )
            mobile = self.job["persona"] == "mobile_vision"
            context = browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                is_mobile=mobile,
                has_touch=mobile,
                user_agent=self.job.get("user_agent"),
            )
            context.set_default_timeout(self.job["step_timeout_seconds"] * 1000)
            self.page = context.new_page()
            self.page.on("console", self._on_console)
            self.page.on("pageerror", lambda exc: self.console_errors.append(str(exc)[:500]))

            allowed = self.job["allowed_actions"]
            reason = "max_steps"
            pending = self.job.get("initial_action")
            while self.step < self.job["max_steps"]:
                if pending is None:
                    self.emit("awaiting_action", step=self.step)
                    line = actions()
                    if line is None:
                        reason = "done"
                        break
                    if not line.strip():
                        continue
                    pending = line
                try:
                    action = parse_action(pending, allowed)
                except (ValueError, json.JSONDecodeError) as exc:
                    self.emit("runner_error", error=f"rejected action: {exc}")
                    pending = None
                    continue
                pending = None
                if action["action"] == "done":
                    reason = "done"
                    break
                self.run_step(action)
            browser.close()
        self.emit("runner_finished", reason=reason, ok=True)
        return 0


def read_line(stream: TextIO) -> str | None:
    line = stream.readline()
    return line if line else None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: runner.py <job.json | ->", file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.readline() if argv[1] == "-" else Path(argv[1]).read_text()
        job = validate_job(json.loads(raw))
    except (ValueError, OSError) as exc:
        sys.stdout.write(json.dumps(make_event("runner_error", {}, error=f"bad job: {exc}")) + "\n")
        return 2
    runner = Runner(job)
    try:
        return runner.run(lambda: read_line(sys.stdin))
    except Exception as exc:
        runner.emit("runner_error", error=f"{type(exc).__name__}: {str(exc)[:500]}")
        runner.emit("runner_finished", reason="error", ok=False)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
