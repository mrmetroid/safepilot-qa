"""Front end 1: the vanilla dashboard the control plane serves at / (the one live on the Vultr VM)."""

from __future__ import annotations

import pytest
from conftest import CONTROL_PLANE, require
from layout import Viewport, check, vision_enabled
from playwright.sync_api import Page, expect

RUN_TIMEOUT_MS = 150_000


def _in_viewport(page: Page, selector: str, viewport: Viewport) -> None:
    el = page.locator(selector)
    expect(el).to_be_visible()
    el.scroll_into_view_if_needed()
    box = el.bounding_box()
    assert box and box["x"] >= -2 and box["x"] + box["width"] <= viewport["width"] + 2, \
        f"{selector} is clipped at {viewport['width']}px: {box}"


def test_start_screen(page: Page, viewport: Viewport) -> None:
    require(CONTROL_PLANE + "/api/health", "control plane")
    page.goto(CONTROL_PLANE + "/")
    for sel in ("#url", "#next", "#preset"):
        _in_viewport(page, sel, viewport)
    s = check(page, "vanilla dashboard", "start", viewport)
    assert s.page_hscroll_px <= 2, f"start screen scrolls sideways by {s.page_hscroll_px}px"


@pytest.mark.live
def test_preset_sweep_end_to_end(page: Page, viewport: Viewport) -> None:
    """Adversarial preset: Box 1 approval gate, Box 3 Containment Receipt, verdict, Copy Fix Prompt."""
    require(CONTROL_PLANE + "/api/health", "control plane")
    if not vision_enabled():
        pytest.skip("VULTR_INFERENCE_API_KEY not set in .env: a live sweep needs Vultr inference")
    page.goto(CONTROL_PLANE + "/")
    page.locator("#preset").click()

    approve = page.locator("#approve")
    expect(approve).to_be_enabled(timeout=RUN_TIMEOUT_MS)
    _in_viewport(page, "#approve", viewport)
    _in_viewport(page, "#block", viewport)
    check(page, "vanilla dashboard", "approval gate", viewport)
    approve.click()

    receipt = page.locator(".receipt.show")
    expect(receipt).to_be_visible(timeout=RUN_TIMEOUT_MS)
    expect(receipt).to_contain_text("secrets_exposed")
    receipt.scroll_into_view_if_needed()
    check(page, "vanilla dashboard", "containment receipt", viewport)

    verdict = page.locator("#verdict-big")
    expect(verdict).to_have_text("DO NOT SHIP", timeout=RUN_TIMEOUT_MS)
    verdict.scroll_into_view_if_needed()
    check(page, "vanilla dashboard", "verdict", viewport)

    copy = page.locator("#copy")
    _in_viewport(page, "#copy", viewport)
    copy.click()
    clip = page.evaluate("navigator.clipboard.readText()")
    assert len(clip) > 100, f"Copy Fix Prompt put {len(clip)} chars on the clipboard"
    page.locator("#annotated").scroll_into_view_if_needed()
    check(page, "vanilla dashboard", "results", viewport)


@pytest.mark.live
def test_custom_url_sweep(page: Page, viewport: Viewport) -> None:
    """Arbitrary public URL through the guided flow: site -> how to test -> deploy -> verdict."""
    require(CONTROL_PLANE + "/api/health", "control plane")
    if not vision_enabled():
        pytest.skip("VULTR_INFERENCE_API_KEY not set in .env: a live sweep needs Vultr inference")
    page.goto(CONTROL_PLANE + "/")
    page.locator("#url").fill("https://example.com")
    page.locator("#next").click()
    expect(page.locator("#screen-how")).to_be_visible(timeout=20_000)
    _in_viewport(page, "#go", viewport)
    check(page, "vanilla dashboard", "how to test", viewport)
    page.locator("#go").click()
    verdict = page.locator("#verdict-big")
    expect(verdict).to_have_text("SHIP IT", timeout=RUN_TIMEOUT_MS)
    verdict.scroll_into_view_if_needed()
    check(page, "vanilla dashboard", "custom verdict", viewport)
