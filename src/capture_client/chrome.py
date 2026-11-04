"""Preview chrome for the crop. This layer is never passed to the final renderer."""

from __future__ import annotations

from PIL import Image, ImageDraw

from .geometry import HANDLE_MARGIN, handle_positions
from .render import load_font


def decorate_crop(image: Image.Image) -> Image.Image:
    """Add a margin, the size label and the adjustment handles around a crop preview."""
    margin = HANDLE_MARGIN
    canvas = Image.new("RGBA", (image.width + margin * 2, image.height + margin * 2), (22, 22, 22, 255))
    canvas.paste(image.convert("RGBA"), (margin, margin))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 2), f"{image.width} × {image.height}", fill=(245, 245, 245, 255), font=load_font(14))
    draw.rectangle(
        (margin, margin, margin + image.width - 1, margin + image.height - 1),
        outline=(245, 245, 245, 255),
    )
    for handle_x, handle_y in handle_positions(image.width, image.height, margin).values():
        draw.rectangle(
            (handle_x - 4, handle_y - 4, handle_x + 4, handle_y + 4),
            fill=(245, 245, 245, 255),
            outline=(20, 20, 20, 255),
        )
    return canvas
