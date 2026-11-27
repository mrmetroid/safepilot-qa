"""Vision bugs the model cannot have seen in the screenshot are dropped before the verdict."""

from app.inference.agents import _off_screen

MOBILE = {"width": 390, "height": 844}


def test_box_entirely_right_of_the_viewport_is_dropped() -> None:
    # droidtech.ai run 799fc8dd: closed slide-in #menu reported at [390, 0, 300, 844].
    assert _off_screen({"bbox": [390, 0, 300, 844]}, MOBILE)


def test_box_entirely_left_or_below_is_dropped() -> None:
    assert _off_screen({"bbox": [-320, 40, 300, 60]}, MOBILE)
    assert _off_screen({"bbox": [10, 900, 100, 40]}, MOBILE)


def test_box_straddling_the_right_edge_is_kept() -> None:
    # demo-target hero CTA: starts at x=24, 460 px wide, clipped by the 390 px viewport.
    assert not _off_screen({"bbox": [24, 252, 366, 58]}, MOBILE)


def test_missing_or_malformed_bbox_is_kept() -> None:
    assert not _off_screen({"bbox": None}, MOBILE)
    assert not _off_screen({"bbox": [1, 2, 3]}, MOBILE)
    assert not _off_screen({}, MOBILE)
