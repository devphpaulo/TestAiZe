"""Stitch one bitmap per monitor. The overlay is never part of this image."""

from __future__ import annotations

from PIL import Image

from .geometry import Monitor, physical_to_stitch, stitch_size


def stitch_bitmaps(parts: list[tuple[Image.Image, Monitor]]) -> Image.Image:
    monitors = [monitor for _, monitor in parts]
    width, height = stitch_size(monitors)
    canvas = Image.new("RGBA", (max(width, 1), max(height, 1)), (0, 0, 0, 255))
    for image, monitor in parts:
        x, y = physical_to_stitch(monitors, monitor.origin_x, monitor.origin_y)
        canvas.paste(image.convert("RGBA"), (x, y))
    return canvas
