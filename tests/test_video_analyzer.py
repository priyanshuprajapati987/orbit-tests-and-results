"""Unit tests for orbit/orbit/core/video_analyzer.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.video_analyzer import VideoAnalyzer, get_video_analyzer


class TestVideoAnalyzer(unittest.TestCase):
    def setUp(self):
        self.v = VideoAnalyzer()

    def test_no_opencv(self):
        with patch.dict(sys.modules, {"cv2": None}):
            r = self.v.analyze("video.mp4")
        self.assertEqual(r["error"], "opencv not installed")
        self.assertEqual(r["frames"], 0)

    def test_analyze_success(self):
        cv2 = MagicMock()
        cap = MagicMock()
        cap.get.side_effect = lambda prop: 30.0 if prop == cv2.CAP_PROP_FPS else 300.0
        cv2.VideoCapture.return_value = cap
        with patch.dict(sys.modules, {"cv2": cv2}):
            v = VideoAnalyzer()
            r = v.analyze("video.mp4")
        self.assertEqual(r["fps"], 30.0)
        self.assertEqual(r["frames"], 300)
        self.assertEqual(r["duration_sec"], 10.0)
        cap.release.assert_called_once()

    def test_analyze_exception(self):
        cv2 = MagicMock()
        cv2.VideoCapture.side_effect = RuntimeError("bad file")
        with patch.dict(sys.modules, {"cv2": cv2}):
            v = VideoAnalyzer()
            r = v.analyze("video.mp4")
        self.assertIn("error", r)

    def test_analyze_zero_fps(self):
        cv2 = MagicMock()
        cap = MagicMock()
        cap.get.side_effect = lambda prop: 0.0 if prop == cv2.CAP_PROP_FPS else 100.0
        cv2.VideoCapture.return_value = cap
        with patch.dict(sys.modules, {"cv2": cv2}):
            v = VideoAnalyzer()
            r = v.analyze("video.mp4")
        self.assertEqual(r["duration_sec"], 0)

    def test_singleton(self):
        a = get_video_analyzer()
        b = get_video_analyzer()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
