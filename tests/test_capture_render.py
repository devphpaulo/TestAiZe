"""Shape output must be smooth without resampling the captured bitmap."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PIL import Image
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
