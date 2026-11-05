"""Tests for Cross-Device Sync (WebSocket), Wake Word Training, Voice Cloning Analysis."""

import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

os.environ["ORBIT_SKIP_STARTUP"] = "1"
os.environ["ORBIT_API_AUTH_ENABLED"] = "0"
sys.path.insert(0, str(Path(__file__).parent.parent))


# ══════════════════════════════════════════════════════════════════════
# Cross-Device Sync — WebSocket Transport
# ══════════════════════════════════════════════════════════════════════


def test_websocket_transport_init():
    from orbit.orbit.core.cross_device_sync import WebSocketTransport

    t = WebSocketTransport("ws://localhost:5001")
    assert t.hub == "ws://localhost:5001"
    assert t._connected is False


def test_websocket_transport_auto_ws_scheme():
    from orbit.orbit.core.cross_device_sync import WebSocketTransport

    t = WebSocketTransport("localhost:5001")
    assert t.hub.startswith("ws://")


def test_websocket_transport_empty_url_raises():
    from orbit.orbit.core.cross_device_sync import WebSocketTransport

    try:
        WebSocketTransport("")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_make_transport_local_default():
    from orbit.orbit.core.cross_device_sync import LocalTransport, _make_transport

    with patch.dict(os.environ, {"SYNC_BACKEND": "local"}):
        t = _make_transport()
        assert isinstance(t, LocalTransport)


def test_make_transport_websocket_no_url_fallback():
    from orbit.orbit.core.cross_device_sync import LocalTransport, _make_transport

    with patch.dict(os.environ, {"SYNC_BACKEND": "websocket", "SYNC_HUB_URL": ""}):
        t = _make_transport()
        assert isinstance(t, LocalTransport)


def test_sync_status_has_device_id():
    from orbit.orbit.core.cross_device_sync import get_cross_device_sync

    sync = get_cross_device_sync()
    status = sync.get_status()
    assert "device_id" in status
    assert len(status["device_id"]) > 0


def test_sync_queue_change():
    from orbit.orbit.core.cross_device_sync import get_cross_device_sync

    sync = get_cross_device_sync()
    sync.queue_change("test", {"msg": "hello"})
    assert len(sync._pending_changes) > 0
    sync._pending_changes.clear()


# ══════════════════════════════════════════════════════════════════════
# Wake Word — Training Data Generation
# ══════════════════════════════════════════════════════════════════════


def test_generate_wake_word_data():
    from orbit.orbit.wake_word import generate_wake_word_data

    with tempfile.TemporaryDirectory() as tmpdir:
        result = generate_wake_word_data(
            wake_phrase="hello jarvis",
            output_dir=tmpdir,
            num_samples=20,
            duration_sec=0.5,
        )
        assert result["positive_samples"] > 0
        assert result["negative_samples"] > 0
        assert result["wake_phrase"] == "hello jarvis"
        # Check files exist
        pos_dir = Path(tmpdir) / "positive"
        neg_dir = Path(tmpdir) / "negative"
        assert len(list(pos_dir.glob("*.wav"))) > 0
        assert len(list(neg_dir.glob("*.wav"))) > 0
        assert (Path(tmpdir) / "metadata.json").exists()


def test_generate_wake_word_data_default_phrase():
    from orbit.orbit.wake_word import generate_wake_word_data

    with tempfile.TemporaryDirectory() as tmpdir:
        result = generate_wake_word_data(
            output_dir=tmpdir, num_samples=10, duration_sec=0.3
        )
        assert result["wake_phrase"] == os.getenv("ORBIT_WAKE_WORD", "orbit")


def test_get_training_data_info_empty():
    from orbit.orbit.wake_word import get_training_data_info

    with (
        tempfile.TemporaryDirectory() as tmpdir,
        patch(
            "orbit.orbit.core.runtime_paths.orbit_data_dir", return_value=Path(tmpdir)
        ),
    ):
        info = get_training_data_info()
        assert info["exists"] is False


def test_get_training_data_info_with_data():
    from orbit.orbit.wake_word import generate_wake_word_data, get_training_data_info

    with tempfile.TemporaryDirectory() as tmpdir:
        wake_dir = os.path.join(tmpdir, "wake_training")
        with patch(
            "orbit.orbit.core.runtime_paths.orbit_data_dir", return_value=Path(tmpdir)
        ):
            generate_wake_word_data(
                output_dir=wake_dir, num_samples=10, duration_sec=0.3
            )
            info = get_training_data_info()
            assert info["exists"] is True
            assert info["positive_samples"] > 0


# ══════════════════════════════════════════════════════════════════════
# Voice Cloning — Quality Analysis
# ══════════════════════════════════════════════════════════════════════


def _create_test_wav(
    path: str, duration: float = 2.0, freq: float = 440, amplitude: int = 10000
):
    """Create a simple sine wave WAV file for testing."""
    rate = 16000
    n_samples = int(rate * duration)
    samples = []
    for i in range(n_samples):
        t = i / rate
        val = int(amplitude * math.sin(2 * math.pi * freq * t))
        samples.append(max(-32768, min(32767, val)))
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def test_analyze_reference_audio():
    from orbit.orbit.xtts import analyze_reference_audio

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "test.wav")
        _create_test_wav(wav_path, duration=3.0, amplitude=8000)
        result = analyze_reference_audio(wav_path)
        assert "scores" in result
        assert "overall" in result["scores"]
        assert result["scores"]["overall"] > 0
        assert "duration_sec" in result
        assert result["duration_sec"] > 2.5


def test_analyze_reference_audio_too_short():
    from orbit.orbit.xtts import analyze_reference_audio

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "short.wav")
        _create_test_wav(wav_path, duration=0.2)
        result = analyze_reference_audio(wav_path)
        assert result["scores"]["duration"] < 0.5


def test_analyze_reference_audio_silent():
    from orbit.orbit.xtts import analyze_reference_audio

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "silent.wav")
        _create_test_wav(wav_path, amplitude=10)
        result = analyze_reference_audio(wav_path)
        assert result["scores"]["overall"] < 0.5


def test_analyze_reference_audio_nonexistent():
    from orbit.orbit.xtts import analyze_reference_audio

    result = analyze_reference_audio("/nonexistent/file.wav")
    assert "error" in result


def test_analyze_all_references_empty():
    from orbit.orbit.xtts import analyze_all_references

    with (
        tempfile.TemporaryDirectory() as tmpdir,
        patch("orbit.orbit.xtts.CLONING_SAMPLES_DIR", Path(tmpdir)),
    ):
        result = analyze_all_references()
        assert result.get("count", 0) == 0 or "No reference audio" in result.get(
            "message", ""
        )


# ══════════════════════════════════════════════════════════════════════
# API Endpoint Tests
# ══════════════════════════════════════════════════════════════════════


def test_api_wake_word_status():
    from orbit.orbit.server import create_app

    app = create_app()
    c = app.test_client()
    r = c.get("/api/voice/wake-word/status")
    assert r.status_code == 200


def test_api_voice_clone_analyze_all():
    from orbit.orbit.server import create_app

    app = create_app()
    c = app.test_client()
    r = c.get("/api/voice/clone/analyze-all")
    assert r.status_code == 200


def test_api_sync_websocket_status():
    from orbit.orbit.server import create_app

    app = create_app()
    c = app.test_client()
    r = c.get("/api/sync/status")
    assert r.status_code == 200
    data = r.get_json()
    assert "device_id" in data


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
