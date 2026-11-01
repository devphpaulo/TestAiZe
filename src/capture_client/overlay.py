"""Overlay rules that do not need Qt: selection visibility and crop gestures."""

from __future__ import annotations

CROP_GEOMETRY_DRAGGING = frozenset({
    "new", "move", "nw", "n", "ne", "e", "se", "s", "sw", "w",
})


def show_capture_chrome(has_region: bool) -> bool:
    """Tools and actions stay hidden until a region exists."""
    return bool(has_region)


def live_screen_during(drag: str | None) -> bool:
    """While the crop moves, the hole in the dim overlay follows the pointer."""
    return drag in CROP_GEOMETRY_DRAGGING
