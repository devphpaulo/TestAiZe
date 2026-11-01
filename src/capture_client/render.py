"""Render the cropped bitmap and its annotations. Controls are not part of this image."""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPainter

from .geometry import Rect, circle_bounds
from .painting import paint_annotation

DEFAULT_STROKE = 4
DEFAULT_FONT_SIZE = 18


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
    if not annotations:
        return image
    pixels = bytearray(image.tobytes())
    canvas = QImage(pixels, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888)
    painter = QPainter(canvas)
    try:
        for note in annotations:
            if note.kind == "text":
                _paint_text(painter, note, clipped)
            else:
                paint_annotation(painter, note, clipped.x, clipped.y)
    finally:
        painter.end()
    return Image.frombytes("RGBA", image.size, bytes(canvas.constBits()))


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _paint_text(painter: QPainter, note: Annotation, crop: Rect) -> None:
    if not note.points or not note.text:
        return
    x, y = note.points[0][0] - crop.x, note.points[0][1] - crop.y
    font = load_font(note.font_size)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = measure.multiline_textbbox((x, y), note.text, font=font)
    left, top = max(0, int(box[0])), max(0, int(box[1]))
    right, bottom = min(crop.width, int(box[2]) + 1), min(crop.height, int(box[3]) + 1)
    if right <= left or bottom <= top:
        return
    tile = Image.new("RGBA", (right - left, bottom - top))
    ImageDraw.Draw(tile).multiline_text((x - left, y - top), note.text, font=font, fill=_parse_color(note.color))
    data = tile.tobytes()
    image = QImage(data, tile.width, tile.height, tile.width * 4, QImage.Format.Format_RGBA8888)
    painter.drawImage(QPointF(left, top), image)
