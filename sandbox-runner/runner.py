"""Canary Swarm sandbox runner.

Untrusted worker that lives inside a disposable, capped Docker container.

Protocol (BUILD_SPEC Section 3.4/3.5):
  stdin  line 1   : job JSON
  stdin  line 2.. : one action JSON per line, sent by the control plane
                    {"action": "click", "selector": "#buy", "value": null, "url": null}
                    {"action": "exit"} ends the session
  stdout          : one JSON event per line (runner_started, step_result,
                    screenshot, console, runner_finished, runner_error)

The runner never decides what to do next. The control plane (trusted
supervisor) plans, filters, and gates every action. The runner holds zero
secrets: its environment only contains image defaults (PATH, HOME=/tmp, ...).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page, sync_playwright

JOB: dict[str, Any] = {}
CONSOLE_BUFFER: list[dict[str, str]] = []

OBSERVE_JS = r"""
(realVw) => {
  // Mobile emulation widens innerWidth to the content width; use the real device viewport.
  const vw = realVw || window.innerWidth, vh = window.innerHeight;
  const clean = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const cssEsc = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : s;
  const selFor = (el) => {
    if (el.id) return '#' + cssEsc(el.id);
    const tid = el.getAttribute('data-testid');
    if (tid) return `[data-testid="${tid}"]`;
    const name = el.getAttribute('name');
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
    const txt = clean(el.innerText || el.value || '', 40);
    if (txt) return `${el.tagName.toLowerCase()}:has-text("${txt.replace(/"/g, '\\"')}")`;
    return el.tagName.toLowerCase();
  };
  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const interactive = Array.from(document.querySelectorAll(
    'a[href], button, input, select, textarea, summary, [role="button"], [onclick]'
  )).filter(isVisible).slice(0, 45).map((el) => {
    const r = el.getBoundingClientRect();
    return {
      sel: selFor(el),
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || undefined,
      text: clean(el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '', 60),
      href: el.getAttribute('href') || undefined,
      rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
    };
  });
  // Layout bugs measured from geometry: elements spilling past the viewport.
  const overflow = [];
  for (const el of document.querySelectorAll('button, a, input, h1, h2, img, [class*="cta"], [class*="btn"]')) {
    if (!isVisible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 2 || r.left < -2) {
      overflow.push({
        sel: selFor(el),
        text: clean(el.innerText || el.value || el.getAttribute('alt') || '', 60),
        rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
        overflow_px: Math.round(Math.max(r.right - vw, -r.left)),
      });
    }
    if (overflow.length >= 8) break;
  }
  // All text nodes incl. hidden ones (injection payloads hide there), minus script/style.
  const hiddenParts = [];
  if (document.body) {
    const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_COMMENT);
    let n, total = 0;
    while ((n = tw.nextNode()) && total < 6000) {
      const p = n.parentElement;
      if (p && (p.tagName === 'SCRIPT' || p.tagName === 'STYLE' || p.tagName === 'NOSCRIPT')) continue;
      const t = (n.nodeValue || '').trim();
      if (t) { hiddenParts.push(t); total += t.length; }
    }
    for (const el of document.querySelectorAll('[aria-label],[title],[alt],meta[content]')) {
      const t = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || el.getAttribute('content');
      if (t && t.length > 20) hiddenParts.push(t);
    }
  }
  return {
    title: document.title,
    url: location.href,
    viewport: [vw, vh],
    scroll_width: document.documentElement.scrollWidth,
    visible_text: clean(document.body ? document.body.innerText : '', 3000),
    // textContent includes hidden nodes: injection payloads often hide there.
    all_text: clean(hiddenParts.join(' '), 4000),
    interactive,
    overflow,
  };
}
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(event_type: str, **fields: Any) -> None:
    payload = {
        "type": event_type,
        "run_id": JOB.get("run_id"),
        "box_id": JOB.get("box_id"),
        "ts": now(),
        **fields,
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def pids_current() -> int | None:
    try:
        with open("/sys/fs/cgroup/pids.current") as fh:
            return int(fh.read().strip())
    except OSError:
        return None


def observe(page: Page, step: int, action: dict[str, Any], ok: bool, error: str | None) -> None:
    """Emit a step_result (DOM + text) and a screenshot for the current page."""
    obs: dict[str, Any] = {}
    try:
        obs = page.evaluate(OBSERVE_JS, (page.viewport_size or {}).get("width"))
    except PWError as exc:
        obs = {"observe_error": str(exc)[:300]}
    console = CONSOLE_BUFFER[:]
    CONSOLE_BUFFER.clear()
    emit(
        "step_result",
        step=step,
        action=action.get("action"),
        selector=action.get("selector"),
        ok=ok,
        error=error,
        console_errors=[c["message"] for c in console if c["level"] == "error"][:10],
        page_url=obs.get("url") or page.url,
        title=obs.get("title"),
        extracted_text=obs.get("visible_text", ""),
        hidden_text=obs.get("all_text", ""),
        dom_summary=obs.get("interactive", []),
        overflow=obs.get("overflow", []),
        scroll_width=obs.get("scroll_width"),
        observe_error=obs.get("observe_error"),
        pids=pids_current(),
    )
    try:
        shot = page.screenshot(type="jpeg", quality=72, timeout=6000)
        vp = page.viewport_size or {}
        emit(
            "screenshot",
            step=step,
            content_type="image/jpeg",
            encoding="base64",
            data=base64.b64encode(shot).decode(),
            width=vp.get("width"),
            height=vp.get("height"),
        )
    except PWError as exc:
        emit("console", level="warning", message=f"screenshot failed: {str(exc)[:200]}")


def execute(page: Page, action: dict[str, Any], timeout_ms: int) -> None:
    kind = action.get("action")
    sel = action.get("selector")
    val = action.get("value")
    if kind == "goto":
        page.goto(action["url"], timeout=timeout_ms * 2, wait_until="domcontentloaded")
    elif kind == "click":
        page.locator(sel).first.click(timeout=timeout_ms)
    elif kind == "fill":
        page.locator(sel).first.fill(str(val or ""), timeout=timeout_ms)
    elif kind == "press":
        if sel:
            page.locator(sel).first.press(str(val or "Enter"), timeout=timeout_ms)
        else:
            page.keyboard.press(str(val or "Enter"))
    elif kind == "hover":
        page.locator(sel).first.hover(timeout=timeout_ms)
    elif kind == "scroll":
        page.mouse.wheel(0, int(val) if str(val or "").lstrip("-").isdigit() else 600)
    elif kind == "wait":
        page.wait_for_timeout(min(int(float(val or 1000)), 3000))
    elif kind == "assert_text":
        page.get_by_text(str(val)).first.wait_for(timeout=timeout_ms)
    elif kind in ("screenshot", "done", "observe"):
        pass
    else:
        raise ValueError(f"action not allowed: {kind}")
    # Give SPA handlers a beat to settle; never block forever on a hostile page.
    try:
        page.wait_for_load_state("domcontentloaded", timeout=2000)
    except PWError:
        pass
    page.wait_for_timeout(350)


def main() -> int:
    global JOB
    first = sys.stdin.readline()
    if not first:
        return 2
    JOB = json.loads(first)
    vp = JOB.get("viewport") or {"width": 1280, "height": 800}
    timeout_ms = int(JOB.get("step_timeout_seconds", 8)) * 1000
    mobile = JOB.get("persona") == "mobile_vision"

    emit("runner_started", pid=os.getpid(), viewport=vp, uid=os.getuid(), pids=pids_current())

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=["--disable-dev-shm-usage", "--disable-gpu", "--no-zygote", "--renderer-process-limit=2"],
        )
        ctx = browser.new_context(
            viewport=vp,
            device_scale_factor=1,  # screenshot px == CSS px, so bboxes line up
            is_mobile=mobile,
            has_touch=mobile,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1 SafePilotQA"
                if mobile
                else None
            ),
        )
        page = ctx.new_page()
        page.on("console", lambda m: CONSOLE_BUFFER.append({"level": m.type, "message": m.text[:300]}))
        page.on("pageerror", lambda e: CONSOLE_BUFFER.append({"level": "error", "message": str(e)[:300]}))

        step = 0
        first_action = {"action": "goto", "url": JOB["target_url"]}
        try:
            execute(page, first_action, timeout_ms)
            observe(page, step, first_action, True, None)
        except Exception as exc:  # noqa: BLE001 - report everything upstream
            observe(page, step, first_action, False, str(exc)[:300])

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                action = json.loads(line)
            except json.JSONDecodeError:
                emit("runner_error", error="bad action json")
                continue
            if action.get("action") == "exit":
                emit("runner_finished", reason=action.get("reason", "done"), ok=True)
                break
            step += 1
            started = time.monotonic()
            try:
                execute(page, action, timeout_ms)
                observe(page, step, action, True, None)
            except Exception as exc:  # noqa: BLE001
                observe(page, step, action, False, f"{type(exc).__name__}: {str(exc)[:240]}")
            if time.monotonic() - started > timeout_ms / 1000 * 3:
                emit("console", level="warning", message="step exceeded budget")
        else:
            emit("runner_finished", reason="stdin_closed", ok=True)
        browser.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        emit("runner_error", error=f"{type(exc).__name__}: {str(exc)[:400]}")
        sys.exit(1)
