"""Planner, mobile vision auditor and Cursor fix-prompt generator.

Every call goes to Vultr Serverless Inference. When the key is missing (local dev)
or a call keeps failing, a deterministic heuristic stands in so the containment,
approval and Docker paths stay testable. Heuristic steps are labelled
source="heuristic" in the UI and /api/health reports inference as not ok.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..config import settings
from . import prompts
from .client import InferenceDisabled, InferenceError, chat_json

log = logging.getLogger("safepilot.agents")


def _fmt_dom(dom: list[dict[str, Any]], limit: int = 40) -> str:
    rows = []
    for el in (dom or [])[:limit]:
        bits = [el.get("sel", ""), el.get("tag", "")]
        if el.get("type"):
            bits.append(f"type={el['type']}")
        bits.append(json.dumps(el.get("text", ""))[:70])
        if el.get("href"):
            bits.append(f"href={el['href'][:60]}")
        rows.append(" | ".join(bits))
    return "\n".join(rows) or "(no interactive elements found)"


def _fmt_history(history: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- step {h.get('step')}: {h.get('action')} {h.get('selector') or h.get('url') or ''} -> {'ok' if h.get('ok') else 'FAILED ' + str(h.get('error') or '')[:80]}"
        for h in history[-6:]
    ) or "(none)"


# --------------------------------------------------------------------------- planner
async def plan(persona: str, obs: dict[str, Any], screenshot_b64: str | None, history: list[dict[str, Any]],
               target_url: str, step: int, max_steps: int, model: str | None = None, focus: str | None = None,
               viewport: dict[str, int] | None = None) -> dict[str, Any]:
    if settings.inference_enabled:
        last = history[-1] if history else None
        goal = prompts.GOALS[persona]
        if viewport:
            goal += f" Viewport: {viewport.get('width')}x{viewport.get('height')}."
        if focus:
            # Operator-supplied test focus. Treated as guidance only; policy checks still apply to every action.
            goal += f" Operator focus for this run: {focus}"
        user = prompts.PLANNER_USER.format(
            persona=persona,
            goal=goal,
            target_url=target_url,
            page_url=obs.get("page_url", ""),
            step=step,
            max_steps=max_steps,
            extracted_text=(obs.get("extracted_text") or "")[:1800],
            dom_summary=_fmt_dom(obs.get("dom_summary") or []),
            history=_fmt_history(history),
            last_action_result=json.dumps({"ok": last.get("ok"), "error": last.get("error")}) if last else "none",
        )
        try:
            out = await chat_json(prompts.PLANNER_SYSTEM, user, screenshot_b64, max_tokens=500, model=model)
            out.setdefault("action", "done")
            out["source"] = "vultr-inference"
            return out
        except (InferenceError, InferenceDisabled) as exc:
            log.warning("planner failed (%s), using heuristic", exc)
            act = heuristic_plan(persona, obs, history)
            act["source"] = "heuristic-after-error"
            act["inference_error"] = str(exc)[:160]
            return act
    act = heuristic_plan(persona, obs, history)
    act["source"] = "heuristic"
    return act


def _find(dom: list[dict[str, Any]], pattern: str, exclude: str | None = None) -> dict[str, Any] | None:
    rx = re.compile(pattern, re.I)
    ex = re.compile(exclude, re.I) if exclude else None
    for el in dom or []:
        hay = f"{el.get('text', '')} {el.get('sel', '')} {el.get('href', '')}"
        if rx.search(hay) and not (ex and ex.search(hay)):
            return el
    return None


def _done_before(history: list[dict[str, Any]], sel: str) -> bool:
    return any(h.get("selector") == sel and h.get("ok") for h in history)


def heuristic_plan(persona: str, obs: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    dom = obs.get("dom_summary") or []
    url = (obs.get("page_url") or "").lower()
    act = lambda a, sel=None, val=None, thought="": {"action": a, "selector": sel, "value": val, "url": None, "thought": thought}  # noqa: E731

    if persona == "happy_path":
        if "checkout" in url:
            for el in dom:
                if el.get("tag") == "input" and el.get("type") in ("text", "email", None) and not _done_before(history, el["sel"]):
                    dummy = "ada@example.test" if "mail" in el["sel"].lower() or el.get("type") == "email" else "Ada Tester"
                    if "card" in el["sel"].lower():
                        dummy = "4242 4242 4242 4242"
                    if "address" in el["sel"].lower():
                        dummy = "Testgatan 1, Stockholm"
                    return act("fill", el["sel"], dummy, "Fill dummy checkout details")
            btn = _find(dom, r"place.?order|pay|purchase|complete|confirm|submit")
            if btn:
                return act("click", btn["sel"], thought="Ready to submit the order (needs human approval)")
        if "cart" in url:
            btn = _find(dom, r"checkout", exclude=r"promo")
            if btn and not _done_before(history, btn["sel"]):
                return act("click", btn["sel"], thought="Proceed to checkout")
        added = any(re.search(r"add|buy|cart", str(h.get("selector")), re.I) and h.get("ok") for h in history)
        if not added:
            btn = _find(dom, r"add to (cart|bag|basket)|add-to-cart|buy")
            if btn:
                return act("click", btn["sel"], thought="Add a product to the cart")
        cart = _find(dom, r"\bcart\b|\bbag\b|basket|checkout", exclude=r"add")
        if cart and not _done_before(history, cart["sel"]):
            return act("click", cart["sel"], thought="Open the cart")
        if len(history) < 2:
            return act("scroll", val="700", thought="Look further down the page")
        return act("done", thought="No further happy-path controls found")

    if persona == "mobile_vision":
        if len(history) == 0:
            return act("scroll", val="0", thought="Capture landing above the fold")
        cart = _find(dom, r"\bcart\b|basket|bag")
        if cart and not _done_before(history, cart["sel"]):
            return act("click", cart["sel"], thought="Check the cart screen at 390px")
        return act("done", thought="Captured landing and cart")

    # chaos_gremlin
    summary = _find(dom, r"promo|coupon|discount|advanced|offer", exclude=r"apply")
    if summary and summary.get("tag") in ("summary", "a", "button") and not _done_before(history, summary["sel"]) \
            and not any(h.get("action") == "fill" for h in history):
        return act("click", summary["sel"], thought="Open the promo / advanced offers control")
    field_ = next((el for el in dom if el.get("tag") == "input" and re.search(r"promo|coupon|discount|code", el.get("sel", "") + el.get("text", ""), re.I)), None)
    if field_ and not _done_before(history, field_["sel"]):
        return act("fill", field_["sel"], "GREMLIN' OR 1=1;--<img src=x>", "Try a hostile promo code")
    apply_ = _find(dom, r"apply|redeem|use code")
    if apply_ and field_ and not _done_before(history, apply_["sel"]):
        return act("click", apply_["sel"], thought="Submit the hostile promo code")
    cart = _find(dom, r"\bcart\b|basket|bag", exclude=r"add")
    if cart and "cart" not in url and not _done_before(history, cart["sel"]):
        return act("click", cart["sel"], thought="Cart pages usually hide promo fields")
    for el in dom:
        if el.get("tag") in ("button", "summary") and not _done_before(history, el["sel"]) and not re.search(r"order|pay|delete|buy", el.get("text", ""), re.I):
            return act("click", el["sel"], thought="Poke an unexplored control")
    return act("done", thought="Nothing left to poke")


# --------------------------------------------------------------------------- vision
def geometry_bugs(obs: dict[str, Any], vw: int = 390) -> list[dict[str, Any]]:
    """Bugs measured directly from the DOM: elements spilling past the viewport width."""
    bugs = []
    for i, o in enumerate(obs.get("overflow") or []):
        x, y, w, h = o["rect"]
        vis_w = max(10, min(x + w, vw) - max(x, 0))
        hidden = o.get("overflow_px", 0)
        sev = "critical" if hidden > 40 and re.search(r"buy|cart|checkout|order|pay", o.get("text", ""), re.I) else "major" if hidden > 20 else "minor"
        bugs.append({
            "id": f"geo-{i + 1}",
            "severity": sev,
            "title": f"{'Primary CTA' if re.search(r'buy|cart|checkout|order|pay', o.get('text', ''), re.I) else 'Element'} clipped: overflows the {vw}px viewport by {hidden}px",
            "description": f"\"{o.get('text') or o.get('sel')}\" ({o.get('sel')}) is {w}px wide at x={x}; {hidden}px are clipped off-screen.",
            "bbox": [max(x, 0), y, vis_w, h],
            "source": "dom-geometry",
        })
    return bugs


def _overlap(a: list[float], b: list[float]) -> float:
    """Intersection over the smaller box."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    small = max(1.0, min(aw * ah, bw * bh))
    return iw * ih / small


_BELOW_FOLD_RE = re.compile(r"\bbottom\b|below the fold|bottom edge|viewport height|vertical(ly)?|scroll", re.I)
_HORIZONTAL_RE = re.compile(r"horizontal|right edge|left edge|width|wider|off-canvas|overflow-x", re.I)


def _below_fold(bug: dict[str, Any], vp: dict[str, int]) -> bool:
    """Viewport screenshots cut the page at the bottom edge; that is scrolling, not clipping.

    Drops vision bugs that touch the bottom edge and describe vertical cut-off without any
    horizontal overflow signal. Measured DOM geometry bugs never go through this filter.
    """
    bb = bug.get("bbox")
    vh = int(vp.get("height") or 844)
    text = f"{bug.get('title', '')} {bug.get('description', '')}"
    touches_bottom = isinstance(bb, list) and len(bb) == 4 and all(isinstance(v, (int, float)) for v in bb) \
        and bb[1] + bb[3] >= vh - 16
    return bool(touches_bottom and _BELOW_FOLD_RE.search(text) and not _HORIZONTAL_RE.search(text))


def _off_screen(bug: dict[str, Any], vp: dict[str, int]) -> bool:
    """A vision bug whose box lies entirely outside the screenshot cannot have been seen in it.

    This happens when the model repeats the DOM hint for an element parked off-canvas (a closed
    slide-in menu at x >= viewport width). Clipping always shows up as a box that overlaps the image.
    """
    bb = bug.get("bbox")
    if not (isinstance(bb, list) and len(bb) == 4 and all(isinstance(v, (int, float)) for v in bb)):
        return False
    x, y, w, h = bb
    vw, vh = int(vp.get("width") or 390), int(vp.get("height") or 844)
    return x >= vw or y >= vh or x + w <= 0 or y + h <= 0


async def audit_mobile(obs: dict[str, Any], screenshot_b64: str | None, viewport: dict[str, int] | None = None,
                       model: str | None = None) -> dict[str, Any]:
    vp = viewport or {"width": 390, "height": 844}
    geo = geometry_bugs(obs, int(vp.get("width") or 390))
    if settings.inference_enabled and screenshot_b64:
        hint = json.dumps([{"sel": o["sel"], "text": o.get("text"), "rect": o["rect"]} for o in obs.get("overflow") or []]) or "[]"
        user = prompts.VISION_USER.format(page_url=obs.get("page_url", ""), dom_hint=hint, vw=vp.get("width"), vh=vp.get("height"))
        try:
            try:
                out = await chat_json(prompts.VISION_SYSTEM, user, screenshot_b64, max_tokens=900, model=model)
            except InferenceError as exc:
                if not model or model == settings.inference_model or isinstance(exc, InferenceDisabled):
                    raise
                # The run's chosen model could not audit this screenshot: retry on the default vision model.
                log.warning("vision audit on %s failed (%s), retrying on %s", model, exc, settings.inference_model)
                out = await chat_json(prompts.VISION_SYSTEM, user, screenshot_b64, max_tokens=900,
                                      model=settings.inference_model)
            bugs = [b for b in out.get("bugs") or []
                    if isinstance(b, dict) and not _below_fold(b, vp) and not _off_screen(b, vp)]
            for b in bugs:
                b["source"] = "vultr-vision"
                bb = b.get("bbox")
                if not (isinstance(bb, list) and len(bb) == 4 and all(isinstance(v, (int, float)) for v in bb)):
                    b["bbox"] = None
            # Measured geometry corroborates vision: add any serious overflow the model did not box.
            for g in geo:
                if g["severity"] in ("critical", "major") and not any(
                        b.get("bbox") and _overlap(b["bbox"], g["bbox"]) > 0.3 for b in bugs):
                    bugs.append(g)
            return {"summary": out.get("summary", ""), "bugs": bugs, "source": "vultr-vision"}
        except (InferenceError, InferenceDisabled) as exc:
            log.warning("vision audit failed: %s", exc)
            return {"summary": f"Vision call failed ({str(exc)[:80]}); geometry check only.", "bugs": geo, "source": "dom-geometry"}
    summary = f"{len(geo)} layout overflow bug(s) measured from DOM geometry." if geo else "No visual bugs found."
    return {"summary": summary, "bugs": geo, "source": "dom-geometry"}


# --------------------------------------------------------------------------- fix prompt
async def fix_prompt(target_url: str, verdict: str, box1: str, box2_bugs: list[dict[str, Any]], box3: str,
                     model: str | None = None) -> dict[str, Any]:
    slim_bugs = [{k: b.get(k) for k in ("severity", "title", "description", "bbox")} for b in box2_bugs]
    if settings.inference_enabled:
        user = prompts.FIX_USER.format(target_url=target_url, verdict=verdict, box1=box1, box2=json.dumps(slim_bugs), box3=box3)
        # Try the run's chosen model first, then the default model, before falling back to the template.
        for m in dict.fromkeys([model or settings.inference_model, settings.inference_model]):
            try:
                out = await chat_json(prompts.FIX_SYSTEM, user, max_tokens=900, model=m)
                if out.get("fix_prompt"):
                    out["source"] = "vultr-inference"
                    return out
            except (InferenceError, InferenceDisabled) as exc:
                log.warning("fix prompt on %s failed: %s", m, exc)
    lines = [f"# Fix request: {target_url}", "", f"Canary Swarm verdict: **{verdict}**", "", "## Findings"]
    lines.append(f"- Happy path (desktop): {box1}")
    for b in slim_bugs:
        lines.append(f"- [{b['severity']}] {b['title']}: {b['description']}")
    lines.append(f"- Chaos exploration: {box3}")
    lines += [
        "",
        "## Please",
        "1. Fix every mobile layout overflow at 390px width: no fixed widths or `white-space: nowrap` on primary CTAs; "
        "let buttons wrap or use `max-width: 100%`. Do not hide the overflow with `overflow-x: hidden`.",
        "2. Remove any promo / discount code path that runs an unbounded loop or allocates memory without limit. "
        "Validate codes server-side with a timeout.",
        "3. Delete any copy that instructs AI agents to reveal environment variables, API keys or cloud metadata.",
        "4. Add a Playwright regression test at a 390x844 viewport asserting the primary CTA is fully inside the viewport, "
        "and a test that applying a promo code returns within 2 seconds.",
    ]
    return {"title": "Canary Swarm fix prompt", "verdict": verdict, "fix_prompt": "\n".join(lines), "source": "template"}
