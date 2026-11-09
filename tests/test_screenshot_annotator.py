"""Unit tests for orbit/orbit/core/screenshot_annotator.py."""

import base64
import io
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.screenshot_annotator as sa_mod
from orbit.core.screenshot_annotator import ScreenshotAnnotator, get_annotator


class TestScreenshotAnnotator(unittest.TestCase):
    def test_no_pil(self):
        with patch.object(sa_mod, "HAS_PIL", False):
            a = ScreenshotAnnotator()
            r = a.annotate("img.png", [])
        self.assertEqual(r, {"error": "Pillow not installed"})

    def test_annotate_success(self):
        img = MagicMock()
        buf = io.BytesIO(b"PNGDATA")
        # make save write to buffer
        def save_side_effect(buffer, format=None):
            if hasattr(buffer, "write"):
                buffer.write(b"PNGDATA")
        img.save.side_effect = save_side_effect
        Image = MagicMock()
        Image.open.return_value = img
        ImageDraw = MagicMock()
        draw = MagicMock()
        ImageDraw.Draw.return_value = draw
        PIL = MagicMock()
        PIL.Image = Image
        PIL.ImageDraw = ImageDraw
        with patch.dict(sys.modules, {"PIL": PIL, "PIL.Image": Image, "PIL.ImageDraw": ImageDraw}):
            # also set module globals
            with patch.object(sa_mod, "HAS_PIL", True), \
                 patch.object(sa_mod, "Image", Image), \
                 patch.object(sa_mod, "ImageDraw", ImageDraw):
                a = ScreenshotAnnotator()
                r = a.annotate("img.png", [
                    {"type": "rectangle", "x1": 0, "y1": 0, "x2": 10, "y2": 10, "color": "red", "width": 2},
                    {"type": "circle", "x1": 0, "y1": 0, "x2": 5, "y2": 5},
                    {"type": "text", "x": 1, "y": 2, "text": "hi", "color": "blue"},
                    {"type": "arrow", "x1": 0, "y1": 0, "x2": 5, "y2": 5, "width": 2},
                    {"type": "highlight", "x1": 0, "y1": 0, "x2": 5, "y2": 5, "color": "yellow"},
                    {"type": "unknown", "x1": 0},
                ])
        self.assertEqual(r["status"], "annotated")
        self.assertEqual(r["path"], "img_annotated.png")
        self.assertEqual(r["annotations_count"], 6)
        self.assertTrue(r["image_base64"].startswith("data:image/png;base64,"))
        img.save.assert_called()  # saved twice (file + buffer)

    def test_annotate_error(self):
        Image = MagicMock()
        Image.open.side_effect = RuntimeError("bad image")
        ImageDraw = MagicMock()
        with patch.object(sa_mod, "HAS_PIL", True), \
             patch.object(sa_mod, "Image", Image), \
             patch.object(sa_mod, "ImageDraw", ImageDraw):
            a = ScreenshotAnnotator()
            r = a.annotate("bad.png", [])
        self.assertIn("error", r)
        self.assertIn("bad image", r["error"])

    def test_singleton(self):
        sa_mod._annotator = None
        a = get_annotator()
        b = get_annotator()
        self.assertIs(a, b)
        sa_mod._annotator = None


if __name__ == "__main__":
    unittest.main()
