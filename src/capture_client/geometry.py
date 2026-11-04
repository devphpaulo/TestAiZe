"""Monitor geometry in physical pixels. Each screen keeps its own scale."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Monitor:
    name: str
    origin_x: int
    origin_y: int
    width: int
    height: int
    scale: float
    dip_x: int = 0
    dip_y: int = 0
    dip_w: int = 0
    dip_h: int = 0

    def contains_physical(self, x: int, y: int) -> bool:
        return self.origin_x <= x < self.origin_x + self.width and self.origin_y <= y < self.origin_y + self.height

    def dip_to_physical(self, dip_x: float, dip_y: float) -> tuple[float, float]:
        return (self.origin_x + dip_x * self.scale, self.origin_y + dip_y * self.scale)


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


def normalize_rect(x: float, y: float, width: float, height: float) -> Rect | None:
    if width < 0:
        x, width = x + width, -width
    if height < 0:
        y, height = y + height, -height
    rect = Rect(int(x), int(y), int(width), int(height))
    if rect.width < 2 or rect.height < 2:
        return None
    return rect


def stitch_origin(monitors: list[Monitor]) -> tuple[int, int]:
    if not monitors:
        return (0, 0)
    return (min(item.origin_x for item in monitors), min(item.origin_y for item in monitors))


def stitch_size(monitors: list[Monitor]) -> tuple[int, int]:
    if not monitors:
        return (0, 0)
    min_x, min_y = stitch_origin(monitors)
    max_x = max(item.origin_x + item.width for item in monitors)
    max_y = max(item.origin_y + item.height for item in monitors)
    return (max_x - min_x, max_y - min_y)


def physical_to_stitch(monitors: list[Monitor], x: int, y: int) -> tuple[int, int]:
    min_x, min_y = stitch_origin(monitors)
    return (x - min_x, y - min_y)


def monitor_at(monitors: list[Monitor], x: int, y: int) -> Monitor | None:
    for item in monitors:
        if item.contains_physical(x, y):
            return item
    return None


def dip_global_to_physical(monitors: list[Monitor], x: float, y: float) -> tuple[int, int]:
    for item in monitors:
        width = item.dip_w or item.width
        height = item.dip_h or item.height
        if item.dip_x <= x < item.dip_x + width and item.dip_y <= y < item.dip_y + height:
            return (
                int(item.origin_x + (x - item.dip_x) * item.scale),
                int(item.origin_y + (y - item.dip_y) * item.scale),
            )
    if not monitors:
        return (int(x), int(y))
    nearest = min(monitors, key=lambda item: abs(item.dip_x - x) + abs(item.dip_y - y))
    return (
        int(nearest.origin_x + (x - nearest.dip_x) * nearest.scale),
        int(nearest.origin_y + (y - nearest.dip_y) * nearest.scale),
    )


def physical_to_dip(monitors: list[Monitor], x: int, y: int) -> tuple[float, float]:
    monitor = monitor_at(monitors, x, y) or (monitors[0] if monitors else None)
    if monitor is None:
        return (float(x), float(y))
    return (
        monitor.dip_x + (x - monitor.origin_x) / monitor.scale,
        monitor.dip_y + (y - monitor.origin_y) / monitor.scale,
    )


HANDLE_MARGIN = 22
HANDLE_RADIUS = 8
_HANDLE_NAMES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


def circle_bounds(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float, float, float]:
    diameter = min(abs(end[0] - start[0]), abs(end[1] - start[1]))
    left = start[0] - diameter if end[0] < start[0] else start[0]
    top = start[1] - diameter if end[1] < start[1] else start[1]
    return left, top, left + diameter, top + diameter


def handle_positions(width: int, height: int, margin: int = HANDLE_MARGIN) -> dict[str, tuple[int, int]]:
    """Positions of the crop handles in a preview that keeps a margin around the bitmap."""
    left, top = margin, margin
    right, bottom = margin + max(width, 1), margin + max(height, 1)
    center_x = margin + max(width, 1) // 2
    center_y = margin + max(height, 1) // 2
    return {
        "nw": (left, top), "n": (center_x, top), "ne": (right, top),
        "e": (right, center_y), "se": (right, bottom), "s": (center_x, bottom),
        "sw": (left, bottom), "w": (left, center_y),
    }


def hit_handle(x: float, y: float, width: int, height: int, margin: int = HANDLE_MARGIN,
               radius: int = HANDLE_RADIUS) -> str | None:
    best = None
    best_distance = radius * radius + 1
    for name, (handle_x, handle_y) in handle_positions(width, height, margin).items():
        distance = (x - handle_x) ** 2 + (y - handle_y) ** 2
        if distance <= radius * radius and distance < best_distance:
            best = name
            best_distance = distance
    return best


def hit_crop_handle(x: float, y: float, rect: Rect, radius: int = HANDLE_RADIUS) -> str | None:
    center_x = rect.x + rect.width / 2
    center_y = rect.y + rect.height / 2
    points = {
        "nw": (rect.x, rect.y), "n": (center_x, rect.y), "ne": (rect.right, rect.y),
        "e": (rect.right, center_y), "se": (rect.right, rect.bottom),
        "s": (center_x, rect.bottom), "sw": (rect.x, rect.bottom), "w": (rect.x, center_y),
    }
    best = None
    best_distance = radius * radius + 1
    for name, (handle_x, handle_y) in points.items():
        distance = (x - handle_x) ** 2 + (y - handle_y) ** 2
        if distance <= radius * radius and distance < best_distance:
            best = name
            best_distance = distance
    return best


def resize_rect(rect: Rect, handle: str, dx: int, dy: int, bounds_width: int, bounds_height: int) -> Rect | None:
    """Resize in original bitmap coordinates. Annotations are not part of this geometry."""
    if handle not in _HANDLE_NAMES:
        return None
    x, y, width, height = float(rect.x), float(rect.y), float(rect.width), float(rect.height)
    if "w" in handle:
        x += dx
        width -= dx
    if "e" in handle:
        width += dx
    if "n" in handle:
        y += dy
        height -= dy
    if "s" in handle:
        height += dy
    normalized = normalize_rect(x, y, width, height)
    if normalized is None:
        return None
    left = max(0, normalized.x)
    top = max(0, normalized.y)
    right = min(bounds_width, normalized.right)
    bottom = min(bounds_height, normalized.bottom)
    return normalize_rect(left, top, right - left, bottom - top)


def move_rect(rect: Rect, dx: int, dy: int, bounds_width: int, bounds_height: int) -> Rect | None:
    x = min(max(0, rect.x + dx), max(0, bounds_width - rect.width))
    y = min(max(0, rect.y + dy), max(0, bounds_height - rect.height))
    return normalize_rect(x, y, rect.width, rect.height)


def tool_side(rect: Rect, bounds_width: int, tool_size: int, gap: int = 12) -> str:
    if rect.right + gap + tool_size <= bounds_width:
        return "right"
    if rect.x - gap - tool_size >= 0:
        return "left"
    return "inside"
