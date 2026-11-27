"""Front end 2: the React dashboard in frontend/ (Vite dev server, proxies /api and /ws to the control plane).

The mock replay (?mock=1) exercises every UI state with no backend; the live test drives a real sweep.
"""

from __future__ import annotations

import pytest
from conftest import CONTROL_PLANE, REACT, require
from layout import Viewport, check, vision_enabled
from playwright.sync_api import Page, expect

RUN_TIMEOUT_MS = 150_000


def _in_viewport(page: Page, selector: str, viewport: Viewport) -> None:
    el = page.locator(selector).first
    expect(el).to_be_visible()
    el.scroll_into_view_if_needed()
    box = el.bounding_box()
    assert box and box["x"] >= -2 and box["x"] + box["width"] <= viewport["width"] + 2, \
        f"{selector} is clipped at {viewport['width']}px: {box}"


def _sweep(page: Page, viewport: Viewport, label: str) -> None:
    page.locator(".btn-preset").click()
    approve = page.locator(".btn-approve").first
    expect(approve).to_be_enabled(timeout=RUN_TIMEOUT_MS)
    _in_viewport(page, ".btn-approve", viewport)
    _in_viewport(page, ".btn-block", viewport)
    check(page, label, "approval gate", viewport)
    approve.click()

    receipt = page.locator("section.receipt")
    expect(receipt).to_be_visible(timeout=RUN_TIMEOUT_MS)
    expect(receipt).to_contain_text("secrets_exposed")
    receipt.scroll_into_view_if_needed()
    check(page, label, "containment receipt", viewport)

    verdict = page.locator(".verdict-word")
    expect(verdict).to_have_text("DO NOT SHIP", timeout=RUN_TIMEOUT_MS)
    verdict.scroll_into_view_if_needed()
    check(page, label, "verdict", viewport)

    _in_viewport(page, ".btn-copy", viewport)
    page.locator(".btn-copy").click()
    clip = page.evaluate("navigator.clipboard.readText()")
    assert len(clip) > 100, f"Copy Fix Prompt put {len(clip)} chars on the clipboard"


def test_start_screen(page: Page, viewport: Viewport) -> None:
    require(REACT + "/", "React dashboard (vite)")
    page.goto(REACT + "/")
    _in_viewport(page, ".urlbar-form input", viewport)
    _in_viewport(page, ".btn-preset", viewport)
    s = check(page, "react dashboard", "start", viewport)
    assert s.page_hscroll_px <= 2, f"start screen scrolls sideways by {s.page_hscroll_px}px"


def test_mock_replay_all_states(page: Page, viewport: Viewport) -> None:
    """UI rehearsal with no backend: gate, receipt, verdict, copy. Not evidence of a real sweep."""
    require(REACT + "/", "React dashboard (vite)")
    page.goto(REACT + "/?mock=1")
    _sweep(page, viewport, "react dashboard (mock)")


@pytest.mark.live
def test_live_preset_sweep(page: Page, viewport: Viewport) -> None:
    require(REACT + "/", "React dashboard (vite)")
    require(CONTROL_PLANE + "/api/health", "control plane")
    if not vision_enabled():
        pytest.skip("VULTR_INFERENCE_API_KEY not set in .env: a live sweep needs Vultr inference")
    page.goto(REACT + "/")
    _sweep(page, viewport, "react dashboard (live)")
