"""Overlay rules that do not need Qt: when chrome appears, and how the person walks back."""

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


def escape_action(has_gesture: bool, has_region: bool) -> str:
    """Right-click and Escape undo the last capture step, then leave."""
    if has_gesture:
        return "clear_gesture"
    if has_region:
        return "clear_region"
    return "leave"
