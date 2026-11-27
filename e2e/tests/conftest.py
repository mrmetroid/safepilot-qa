"""Fixtures: one browser page per (test, viewport), and the local URLs of the three front ends.

Start the stack first with `scripts/dev.sh --react`. Front ends that are not reachable are skipped with a reason.
"""

from __future__ import annotations

import os
import urllib.request
from collections.abc import Iterator

import pytest
from layout import Viewport, write_report
from playwright.sync_api import Browser, Page

CONTROL_PLANE = os.environ.get("SAFEPILOT_URL", "http://127.0.0.1:8000").rstrip("/")
REACT = os.environ.get("SAFEPILOT_REACT_URL", "http://127.0.0.1:5173").rstrip("/")
DEMO_TARGET = os.environ.get("SAFEPILOT_DEMO_URL", "http://127.0.0.1:8081/demo-target/")

VIEWPORTS: dict[str, Viewport] = {
    "mobile": {"width": 390, "height": 844},
    "desktop": {"width": 1280, "height": 800},
}


def _reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status < 500
    except Exception:  # noqa: BLE001
        return False


def require(url: str, what: str) -> None:
    if not _reachable(url):
        pytest.skip(f"{what} not reachable at {url} (start it with scripts/dev.sh --react)")


@pytest.fixture(params=list(VIEWPORTS), ids=list(VIEWPORTS))
def viewport(request: pytest.FixtureRequest) -> Viewport:
    return VIEWPORTS[request.param]


@pytest.fixture
def page(browser: Browser, viewport: Viewport) -> Iterator[Page]:
    mobile = viewport["width"] < 600
    # device_scale_factor=1 keeps screenshot pixels == CSS pixels, so vision bboxes and DOM rects share one space.
    ctx = browser.new_context(viewport=viewport, device_scale_factor=1, is_mobile=mobile, has_touch=mobile)
    ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    pg = ctx.new_page()
    yield pg
    ctx.close()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    text = write_report()
    if text:
        print("\n\n" + text)
