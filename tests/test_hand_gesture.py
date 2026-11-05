import os
import time

import pytest


def _make_landmarks(extended=None, thumb_extended=True):
    """Build a MediaPipe-shaped landmark dict where extended fingers point far
    from the wrist and tucked fingers stay near it."""
    extended = extended or {}
    lm = {"wrist": (0, 0), "palm_center": (20, -20)}
    for name in ("thumb", "index", "middle", "ring", "pinky"):
        e = extended.get(name, False)
        lm[f"{name}_tip"] = (40, -160) if e else (8, -30)
        lm[f"{name}_pip"] = (30, -80) if e else (8, -30)
        lm[f"{name}_mcp"] = (15, -30)
    if thumb_extended:
        lm["thumb_tip"] = (40, -160)
        lm["thumb_ip"] = (30, -80)
        lm["thumb_cmc"] = (15, -30)
    else:
        lm["thumb_tip"] = (8, -30)
        lm["thumb_ip"] = (8, -30)
        lm["thumb_cmc"] = (15, -30)
    return lm


class TestClassifier:
    @pytest.fixture(autouse=True)
    def _engine(self):
        from orbit.orbit.core.hand_gesture import HandGestureRecognizer

        self.engine = HandGestureRecognizer()

    @pytest.mark.parametrize(
        "gesture,extended,thumb",
        [
            ("fist", {}, False),
            (
                "open_palm",
                {"index": True, "middle": True, "ring": True, "pinky": True},
                False,
            ),
            (
                "spider",
                {"index": True, "middle": True, "ring": True, "pinky": True},
                True,
            ),
            ("pointing", {"index": True}, False),
            ("victory", {"index": True, "middle": True}, False),
            ("three", {"index": True, "middle": True, "ring": True}, False),
            ("thumbs_up", {}, True),
        ],
    )
    def test_static_gestures(self, gesture, extended, thumb):
        lm = _make_landmarks(extended, thumb_extended=thumb)
        g, _ = self.engine.classify(lm)
        assert g == gesture

    def test_pinch_requires_tucked_others(self):
        lm = _make_landmarks({"index": True, "thumb": True})
        lm["index_tip"] = (39, -159)  # touching the thumb
        g, _ = self.engine.classify(lm)
        assert g == "pinch"

    def test_gun(self):
        lm = _make_landmarks({"index": True, "thumb": True})
        lm["thumb_tip"] = (30, -160)
        lm["index_tip"] = (50, -160)
        g, _ = self.engine.classify(lm)
        assert g == "gun"

    def test_open_palm_not_pinch(self):
        lm = _make_landmarks(
            {"index": True, "middle": True, "ring": True, "pinky": True},
            thumb_extended=False,
        )
        g, _ = self.engine.classify(lm)
        assert g == "open_palm"

    def test_empty_landmarks(self):
        g, c = self.engine.classify({})
        assert g is None
        assert c == 0.0

    def test_confidence_positive(self):
        lm = _make_landmarks({"index": True})
        _, c = self.engine.classify(lm)
        assert c >= 0.8


class TestConfigAndState:
    @pytest.fixture(autouse=True)
    def _engine(self):
        from orbit.orbit.core.hand_gesture import HandGestureRecognizer

        self.engine = HandGestureRecognizer()

    def test_set_config(self):
        res = self.engine.set_config({"sensitivity": 0.8, "debounce": 5})
        assert res["ok"] is True
        assert self.engine.get_config()["sensitivity"] == 0.8

    def test_action_map_merge(self):
        self.engine.set_config({"actions": {"fist": "screenshot"}})
        cfg = self.engine.get_config()
        assert cfg["action_map"]["fist"] == "screenshot"
        assert cfg["action_map"]["wave"]  # default preserved

    def test_reset(self):
        self.engine._history.append({"gesture": "fist"})
        self.engine._last_gesture = "fist"
        self.engine.reset()
        assert self.engine._last_gesture is None
        assert len(self.engine._history) == 0

    def test_schema(self):
        schema = self.engine.get_config_schema()
        assert "gestures" in schema
        assert "wave" in schema["dynamic"]
        assert "fist" in schema["gestures"]

    def test_parse_action(self):
        parsed = self.engine._parse_action("speak_emotion:Great job!:happy")
        assert parsed["kind"] == "speak_emotion"
        assert parsed["parts"] == ["Great job!", "happy"]

    def test_stats_shape(self):
        stats = self.engine.get_stats()
        assert "backend" in stats
        assert "running" in stats
        assert "detections" in stats


class TestActionExecution:
    @pytest.fixture(autouse=True)
    def _engine(self):
        from orbit.orbit.core.hand_gesture import HandGestureRecognizer

        self.engine = HandGestureRecognizer()
        self.engine._last_action_at = {}

    def test_guard_blocks_spam(self, monkeypatch):
        calls = []

        def fake_action(action):
            calls.append(action)

        monkeypatch.setattr(self.engine, "_execute_action", fake_action)
        self.engine._run_action("fist")
        self.engine._run_action("fist")  # within guard window -> skipped
        assert len(calls) == 1

    def test_guard_allows_after_grace(self, monkeypatch):
        calls = []

        def fake_action(action):
            calls.append(action)

        monkeypatch.setattr(self.engine, "_execute_action", fake_action)
        self.engine._last_action_at["speech"] = time.monotonic() - 10
        self.engine._run_action("fist")
        assert len(calls) == 1

    def test_unknown_gesture_noop(self):
        self.engine._config["action_map"] = {}
        assert self.engine._run_action("fist") is None

    def test_stop_speech_action(self, monkeypatch):
        stopped = []

        class Fake:
            def stop(self):
                stopped.append(True)

        monkeypatch.setattr(self.engine, "_stop_speech", lambda: stopped.append(True))
        self.engine._last_action_at = {}
        self.engine._execute_action({"kind": "stop_speech", "parts": []})
        assert stopped


@pytest.mark.skipif(
    os.getenv("ORBIT_TEST_FLASK", "0") == "0",
    reason="Flask app test requires ORBIT_TEST_FLASK=1 (heavy import)",
)
class TestAPI:
    def test_gestures_endpoints(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/gestures/status")
        assert r.status_code == 200
        assert "backend" in r.get_json()
        r = client.get("/api/gestures/config/schema")
        assert r.status_code == 200
        r = client.post("/api/gestures/config", json={"sensitivity": 1.0})
        assert r.status_code == 200
        r = client.get("/api/gestures/frame")
        assert r.status_code == 404  # no camera in test env
