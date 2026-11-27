"""The overflow rule in sandbox-runner/runner.py (what Box 2 measures), run in a real browser.

One synthetic 390px page holds the three cases: a closed slide-in menu parked past the right edge,
a horizontal carousel, and a CTA that straddles the edge. Only the CTA is a clipping bug.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from layout import MEASURE_JS
from playwright.sync_api import Browser

RUNNER = Path(__file__).resolve().parents[2] / "sandbox-runner" / "runner.py"

PAGE = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  html { overflow-x: hidden; } body { margin: 0; font: 16px sans-serif; }
  #menu { position: fixed; top: 0; left: 100%; width: 300px; height: 100vh; }
  .carousel { display: flex; overflow-x: auto; gap: 8px; }
  .carousel a { flex: none; width: 200px; }
  .cta { display: inline-block; width: 460px; margin-left: 24px; white-space: nowrap; }
</style></head><body>
  <nav id="menu"><a href="#a">About</a><a href="#c">Contact</a></nav>
  <div class="carousel"><a href="#1">One</a><a href="#2">Two</a><a href="#3">Three</a></div>
  <a class="cta" id="buy" href="#buy">Buy the Harbor Blend now</a>
</body></html>"""


def _runner_observe_js() -> str:
    spec = importlib.util.spec_from_file_location("sandbox_runner", RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.OBSERVE_JS


def _flagged(browser: Browser, js: str) -> list[str]:
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1,
                              is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.set_content(PAGE)
    obs = page.evaluate(js, 390)
    ctx.close()
    return [o["sel"] for o in obs["overflow"]]


def test_runner_flags_only_the_straddling_cta(browser: Browser) -> None:
    assert _flagged(browser, _runner_observe_js()) == ["#buy"]


def test_e2e_measure_matches_the_runner(browser: Browser) -> None:
    assert _flagged(browser, MEASURE_JS) == ["#buy"]
