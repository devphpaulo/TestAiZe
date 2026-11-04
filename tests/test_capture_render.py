"""Shape output must be smooth without resampling the captured bitmap."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PIL import Image, ImageChops, ImageDraw
from capture_client.geometry import Rect
from capture_client.render import Annotation, render_capture


class SmoothRenderTests(unittest.TestCase):
    def test_shapes_have_antialiased_edges_and_leave_background_pixels_intact(self):
        base = Image.new("RGBA", (100, 90), (255, 255, 255, 255))
        for kind in ("line", "arrow", "rect", "circle", "free"):
            with self.subTest(kind=kind):
                image = render_capture(base, Rect(0, 0, 100, 90), [
                    Annotation(kind, "#E10600", [(20, 20), (75, 63)])])
                self.assertEqual(image.size, base.size)
                self.assertEqual(image.getpixel((3, 3)), base.getpixel((3, 3)))
                self.assertEqual(base.getpixel((40, 40)), (255, 255, 255, 255))
                self.assertTrue(any(6 < pixel[1] < 255 for pixel in image.get_flattened_data()))

    def test_empty_annotations_preserve_all_bitmap_bytes(self):
        raw = bytes((i * 31) % 256 for i in range(80 * 60 * 4))
        base = Image.frombytes("RGBA", (80, 60), raw)
        self.assertEqual(render_capture(base, Rect(0, 0, 80, 60), []).tobytes(), raw)

    def test_blur_clips_reversed_drag_to_crop_and_preserves_outside_pixels(self):
        base = Image.new("RGBA", (80, 60), "white")
        ImageDraw.Draw(base).rectangle((20, 0, 39, 59), fill="black")
        crop = Rect(10, 10, 50, 40)
        original = render_capture(base, crop, [])
        blurred = render_capture(base, crop, [Annotation("blur", "", [(50, 40), (0, 20)])])
        difference = ImageChops.difference(original.convert("RGB"), blurred.convert("RGB"))
        self.assertEqual(difference.getbbox(), (0, 10, 40, 30))
        self.assertGreater(blurred.getpixel((29, 20))[0], 0)
        self.assertLess(blurred.getpixel((30, 20))[0], 255)
        self.assertEqual(base.getpixel((39, 30)), (0, 0, 0, 255))
