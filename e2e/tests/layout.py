"""Layout measurement and the Vultr vision check shared by every front-end test.

One sample = one rendered screen (front end + page/state + viewport): a viewport screenshot plus the DOM
geometry measured from the same render. Two independent verdicts are recorded per sample:

- dom: elements spilling past the left/right viewport edge, plus page-level horizontal scroll.
- vision: the product's own Mobile Vision audit (app.inference.agents.audit_mobile) on Vultr Serverless Inference.

The report keeps both, whether they agree, and an annotated PNG (red = vision, blue = DOM) for a human to look at.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from PIL import Image, ImageDraw
from playwright.sync_api import Page

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "e2e" / "report"
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import settings
from app.inference import agents


class Viewport(TypedDict):
    width: int
    height: int


class Overflow(TypedDict):
    sel: str
    text: str
    rect: list[int]
    overflow_px: int


class Bug(TypedDict, total=False):
    id: str
    severity: str
    title: str
    description: str
    bbox: list[float] | None
    source: str


# Same element set and rule as sandbox-runner/runner.py, so the test measures what Box 2 measures.
MEASURE_JS = """(deviceWidth) => {
  // Mobile emulation widens innerWidth to the content width; use the real device viewport (as runner.py does).
  const vw = deviceWidth || window.innerWidth;
  const clean = (s, n) => (s || '').replace(/\\s+/g, ' ').trim().slice(0, n);
  const selFor = (el) => el.id ? '#' + el.id : el.tagName.toLowerCase() +
    (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  // Inside a horizontal scroller (carousel, filmstrip) content past the edge is reachable by scrolling, not clipped.
  // Clipping by overflow:hidden (including html/body) still counts.
  const inScroller = (el) => {
    for (let p = el.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === 'auto' || ox === 'scroll') return true;
    }
    return false;
  };
  const overflow = [];
  for (const el of document.querySelectorAll('button, a, input, h1, h2, img, [class*="cta"], [class*="btn"]')) {
    if (!visible(el) || inScroller(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 2 || r.left < -2) overflow.push({
      sel: selFor(el), text: clean(el.innerText || el.value || el.getAttribute('alt') || '', 60),
      rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
      overflow_px: Math.round(Math.max(r.right - vw, -r.left)) });
    if (overflow.length >= 8) break;
  }
  const se = document.scrollingElement || document.documentElement;
  return { page_url: location.href, overflow, scroll_width: se.scrollWidth, inner_width: vw,
           html_overflow_x: getComputedStyle(document.documentElement).overflowX };
}"""


@dataclass
class Sample:
    name: str
    frontend: str
    viewport: Viewport
    page_url: str
    page_hscroll_px: int
    dom_bugs: list[Bug]
    vision_bugs: list[Bug] = field(default_factory=list)
    vision_summary: str = ""
    vision_source: str = "skipped"  # vultr-vision | dom-geometry (vision call failed) | skipped (no key)
    screenshot: str = ""
    annotated: str = ""

    @property
    def dom_flags(self) -> bool:
        return self.page_hscroll_px > 2 or any(b["severity"] in ("critical", "major") for b in self.dom_bugs)

    @property
    def vision_flags(self) -> bool | None:
        if self.vision_source != "vultr-vision":
            return None
        return any(b.get("severity") in ("critical", "major") and b.get("source") == "vultr-vision"
                   for b in self.vision_bugs)

    def to_json(self) -> dict[str, Any]:
        return {**asdict(self), "dom_flags": self.dom_flags, "vision_flags": self.vision_flags}


SAMPLES: list[Sample] = []


def vision_enabled() -> bool:
    # A FAKE placeholder copied from .env.local.example counts as not set.
    return settings.inference_enabled and not settings.inference_api_key.upper().startswith("FAKE")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _annotate(png: Path, out: Path, vision: list[Bug], dom: list[Bug]) -> None:
    img = Image.open(png).convert("RGB")
    draw = ImageDraw.Draw(img)
    for bugs, color in ((dom, (40, 110, 255)), (vision, (255, 0, 0))):
        for b in bugs:
            bb = b.get("bbox")
            if bb and len(bb) == 4:
                x, y, w, h = (float(v) for v in bb)
                draw.rectangle([x, y, x + w, y + h], outline=color, width=3)
    img.save(out)


def check(page: Page, frontend: str, state: str, viewport: Viewport) -> Sample:
    """Screenshot + DOM geometry + (if a key is configured) the product's Vultr vision audit for one screen."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{frontend} | {state} | {viewport['width']}x{viewport['height']}"
    base = REPORT_DIR / _slug(name)
    png = base.with_suffix(".png")
    page.screenshot(path=str(png))  # viewport only: the same view the vision model gets in the product
    obs: dict[str, Any] = page.evaluate(MEASURE_JS, viewport["width"])
    dom = agents.geometry_bugs(obs, viewport["width"])
    sample = Sample(name=name, frontend=frontend, viewport=viewport, page_url=obs["page_url"],
                    page_hscroll_px=max(0, obs["scroll_width"] - obs["inner_width"]), dom_bugs=dom,
                    screenshot=png.name)
    if vision_enabled():
        b64 = base64.b64encode(png.read_bytes()).decode()
        audit = asyncio.run(agents.audit_mobile(obs, b64, dict(viewport), None))
        sample.vision_bugs = audit["bugs"]
        sample.vision_summary = audit.get("summary", "")
        sample.vision_source = audit.get("source", "dom-geometry")
    annotated = base.with_name(base.name + "-annotated.png")
    _annotate(png, annotated, [b for b in sample.vision_bugs if b.get("source") == "vultr-vision"], dom)
    sample.annotated = annotated.name
    SAMPLES.append(sample)
    return sample


def write_report() -> str:
    """Write report/samples.json and report/summary.md; return the summary text."""
    if not SAMPLES:
        return ""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "samples.json").write_text(json.dumps([s.to_json() for s in SAMPLES], indent=1))
    judged = [s for s in SAMPLES if s.vision_flags is not None]
    agree = [s for s in judged if s.vision_flags == s.dom_flags]
    lines = [
        "# SafePilot front-end check",
        "",
        f"- samples (screens checked): {len(SAMPLES)}",
        f"- Vultr vision calls that returned a verdict: {len(judged)}"
        + ("" if vision_enabled() else "  (VULTR_INFERENCE_API_KEY not set: vision skipped)"),
        f"- vision verdict agrees with DOM geometry: {len(agree)}/{len(judged)}",
        "",
        "| screen | page h-scroll px | DOM flags | vision flags | vision bugs | annotated |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for s in SAMPLES:
        vb = "; ".join(f"{b.get('severity')}: {b.get('title')}" for b in s.vision_bugs if b.get("source") == "vultr-vision")
        vf = "n/a" if s.vision_flags is None else ("YES" if s.vision_flags else "no")
        lines.append(f"| {s.name} | {s.page_hscroll_px} | {'YES' if s.dom_flags else 'no'} | {vf} | "
                     f"{vb or '-'} | {s.annotated} |")
    text = "\n".join(lines) + "\n"
    (REPORT_DIR / "summary.md").write_text(text)
    return text
