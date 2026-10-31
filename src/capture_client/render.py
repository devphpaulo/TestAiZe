"""Render the cropped bitmap and its annotations. Controls are not part of this image."""

from __future__ import annotations

import io
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .geometry import Rect

DEFAULT_STROKE = 4
DEFAULT_FONT_SIZE = 18
ARROW_HEAD = 16


def font_path() -> Path | None:
    roots = [Path(__file__).resolve().parent]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.insert(0, Path(meipass) / "capture_client")
    candidates = [root / "fonts" / "DejaVuSans.ttf" for root in roots]
    candidates.extend([
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_font(size: int = DEFAULT_FONT_SIZE) -> ImageFont.ImageFont:
    path = font_path()
    if path is not None:
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


@dataclass
class Annotation:
    kind: str
    color: str
    points: list[tuple[float, float]] = field(default_factory=list)
    text: str = ""
    stroke: int = DEFAULT_STROKE
    font_size: int = DEFAULT_FONT_SIZE

    def copy(self) -> "Annotation":
        return Annotation(self.kind, self.color, list(self.points), self.text, self.stroke, self.font_size)


def _parse_color(value: str) -> tuple[int, int, int, int]:
    raw = value.removeprefix("#")
    if len(raw) != 6:
        raw = "E10600"
    red = int(raw[0:2], 16)
    green = int(raw[2:4], 16)
    blue = int(raw[4:6], 16)
    return (red, green, blue, 255)


def render_capture(base: Image.Image, crop: Rect, annotations: list[Annotation]) -> Image.Image:
    """Return only the crop plus annotations. No handles, labels or panels."""
    if crop.width < 2 or crop.height < 2:
        raise ValueError("Região vazia.")
    source = base.convert("RGBA")
    clipped = Rect(
        max(0, crop.x),
        max(0, crop.y),
        max(0, min(source.width, crop.right) - max(0, crop.x)),
        max(0, min(source.height, crop.bottom) - max(0, crop.y)),
    )
    if clipped.width < 2 or clipped.height < 2:
        raise ValueError("Região vazia.")
    image = source.crop((clipped.x, clipped.y, clipped.right, clipped.bottom))
    draw = ImageDraw.Draw(image)
    offset_x = clipped.x
    offset_y = clipped.y
    for note in annotations:
        _draw_annotation(draw, note, offset_x, offset_y)
    return image


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _local(points: list[tuple[float, float]], offset_x: int, offset_y: int) -> list[tuple[float, float]]:
    return [(x - offset_x, y - offset_y) for x, y in points]


def _draw_annotation(draw: ImageDraw.ImageDraw, note: Annotation, offset_x: int, offset_y: int) -> None:
    color = _parse_color(note.color)
    points = _local(note.points, offset_x, offset_y)
    stroke = max(1, note.stroke)
    if note.kind == "rect" and len(points) >= 2:
        draw.rectangle((*points[0], *points[1]), outline=color, width=stroke)
    elif note.kind == "line" and len(points) >= 2:
        draw.line((*points[0], *points[1]), fill=color, width=stroke)
    elif note.kind == "arrow" and len(points) >= 2:
        _draw_arrow(draw, points[0], points[1], color, stroke)
    elif note.kind == "circle" and len(points) >= 2:
        start, end = points[0], points[1]
        radius = min(abs(end[0] - start[0]), abs(end[1] - start[1])) / 2
        if radius < 1:
            return
        center = (start[0] + math.copysign(radius, end[0] - start[0]),
                  start[1] + math.copysign(radius, end[1] - start[1]))
        box = (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius)
        draw.ellipse(box, outline=color, width=stroke)
    elif note.kind == "free" and len(points) >= 2:
        draw.line(points, fill=color, width=stroke, joint="curve")
    elif note.kind == "text" and points and note.text:
        draw.text(points[0], note.text, fill=color, font=load_font(note.font_size))


def _draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float],
                color: tuple[int, int, int, int], stroke: int) -> None:
    draw.line((start, end), fill=color, width=stroke)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    length = max(ARROW_HEAD, stroke * 4)
    spread = math.radians(28)
    left = (end[0] - length * math.cos(angle - spread), end[1] - length * math.sin(angle - spread))
    right = (end[0] - length * math.cos(angle + spread), end[1] - length * math.sin(angle + spread))
    draw.polygon((end, left, right), fill=color)
