"""Front end 3: the built-in demo-target shop. It is also the instrument control for the layout check.

- mobile home is broken on purpose (.hero-cta is 460px wide and html{overflow-x:hidden} clips it): both DOM
  geometry and Vultr vision MUST flag it. If they do not, the checker is broken, not the page.
- desktop home is the clean control: neither check may report a critical bug there.

Never touch the promo field: its chaos script starts a runaway loop on purpose (that is Box 3's job, in a sandbox).
"""

from __future__ import annotations

from conftest import DEMO_TARGET, require
from layout import Viewport, check, vision_enabled
from playwright.sync_api import Page, expect


def _overlaps(a: list[float], b: list[float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return min(ax + aw, bx + bw) > max(ax, bx) and min(ay + ah, by + bh) > max(ay, by)


def test_home_layout_control(page: Page, viewport: Viewport) -> None:
    require(DEMO_TARGET, "demo-target")
    page.goto(DEMO_TARGET)
    expect(page.locator("#hero-buy")).to_be_visible()
    s = check(page, "demo-target", "home", viewport)
    if viewport["width"] < 600:
        cta = [b for b in s.dom_bugs if "hero" in (b.get("description") or "").lower() or "buy" in b["title"].lower()]
        assert cta, f"positive control: DOM geometry must flag the clipped hero CTA at 390px, got {s.dom_bugs}"
        if vision_enabled():
            vision = [b for b in s.vision_bugs if b.get("source") == "vultr-vision" and b.get("bbox")]
            assert any(_overlaps(v["bbox"], c["bbox"]) for v in vision for c in cta), (
                f"positive control: Vultr vision must box the clipped hero CTA. vision={vision} dom={cta}")
    else:
        assert not s.dom_flags, f"negative control: desktop home must be clean, DOM says {s.dom_bugs}"
        if vision_enabled():
            critical = [b for b in s.vision_bugs if b.get("severity") == "critical"]
            assert not critical, f"negative control: Vultr vision reports critical bugs on clean desktop home: {critical}"


def test_checkout_flow_reaches_place_order(page: Page, viewport: Viewport) -> None:
    """Box 1's path: add to cart -> cart -> checkout. Stops at Place order (the irreversible action)."""
    require(DEMO_TARGET, "demo-target")
    page.goto(DEMO_TARGET)
    page.locator("#add-harbor-blend").click()
    expect(page.locator("#cart-count")).to_have_text("1")
    page.locator("#nav-cart").click()
    check(page, "demo-target", "cart", viewport)
    page.locator("#go-checkout").click()
    place = page.locator("#place-order")
    expect(place).to_be_visible()
    place.scroll_into_view_if_needed()
    box = place.bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"] + 2, \
        f"Place order button is off-screen at {viewport['width']}px: {box}"
    check(page, "demo-target", "checkout", viewport)


def test_signup_form_usable(page: Page, viewport: Viewport) -> None:
    require(DEMO_TARGET, "demo-target")
    page.goto(DEMO_TARGET + "signup.html")
    for sel in ("#name", "#email", "#password", "#create-account"):
        expect(page.locator(sel)).to_be_visible()
    check(page, "demo-target", "signup", viewport)
