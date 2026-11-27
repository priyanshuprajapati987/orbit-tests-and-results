"""Deep tests for orbit/orbit/streaming_tts.py (Loop 19/1)."""

import asyncio
import unittest
from unittest import mock

from orbit.orbit import streaming_tts as st


class StreamingChunkTTSConfigTests(unittest.TestCase):
    def test_streaming_chunk_defaults(self):
        c = st.StreamingChunk()
        self.assertEqual(c.audio_data, b"")
        self.assertEqual(c.index, 0)
        self.assertFalse(c.is_final)
        self.assertEqual(c.duration_ms, 0.0)

    def test_tts_config_defaults(self):
        c = st.TTSConfig()
        self.assertEqual(c.engine, "edge-tts")
        self.assertEqual(c.voice, "en-GB-RyanNeural")
        self.assertEqual(c.speed, 1.0)
        self.assertEqual(c.language, "en")
        self.assertEqual(c.emotion, "neutral")
        self.assertIsNone(c.reference_audio)
        self.assertEqual(c.fish_api_key, "")
        self.assertEqual(c.fish_api_url, "https://api.fish.audio/v1/tts")
        self.assertEqual(c.cosyvoice_api_url, "")
        self.assertEqual(c.sample_rate, 24000)


class DetectEnginesTests(unittest.TestCase):
    def test_detect_with_httpx_available(self):
        with mock.patch.dict("sys.modules", {"httpx": mock.MagicMock(),
                                            "edge_tts": mock.MagicMock(),
                                            "sounddevice": mock.MagicMock()}):
            tts = st.StreamingTTS()
        self.assertTrue(tts._engines_available["httpx"])
        self.assertTrue(tts._engines_available["edge_tts"])
        self.assertTrue(tts._engines_available["sounddevice"])

    def test_httpx_import_missing(self):
        import importlib
        with mock.patch.dict("sys.modules", {"httpx": None}):
            importlib.reload(st)
            self.assertFalse(st._HTTPX_AVAILABLE)
        # restore
        importlib.reload(st)

    def test_detect_edge_tts_missing(self):
        with mock.patch.dict("sys.modules", {"httpx": mock.MagicMock(),
                                            "edge_tts": None,
                                            "sounddevice": mock.MagicMock()}):
            tts = st.StreamingTTS()
        self.assertFalse(tts._engines_available["edge_tts"])

    def test_detect_sounddevice_missing(self):
        with mock.patch.dict("sys.modules", {"httpx": mock.MagicMock(),
                                            "edge_tts": mock.MagicMock(),
                                            "sounddevice": None}):
            tts = st.StreamingTTS()
        self.assertFalse(tts._engines_available["sounddevice"])

    def test_custom_config(self):
        cfg = st.TTSConfig(engine="fish", speed=1.5)
        tts = st.StreamingTTS(config=cfg)
        self.assertIs(tts.config, cfg)


class SpeakTests(unittest.TestCase):
    def test_speak_first_engine_success(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig()
        tts._lock = __import__("threading").Lock()
        tts._engines_available = {"edge_tts": True}
        with mock.patch.object(tts, "_speak_fish", return_value={"success": False}), \
                mock.patch.object(tts, "_speak_cosyvoice", return_value={"success": False}), \
                mock.patch.object(tts, "_speak_edge", return_value={"success": True, "audio_data": b"x"}):
            r = tts.speak("hi")
        self.assertTrue(r["success"])
        self.assertEqual(r["engine_used"], "edge")

    def test_speak_all_fail(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig()
        tts._lock = __import__("threading").Lock()
        tts._engines_available = {}
        with mock.patch.object(tts, "_speak_fish", return_value={"success": False}), \
                mock.patch.object(tts, "_speak_cosyvoice", return_value={"success": False}), \
                mock.patch.object(tts, "_speak_edge", return_value={"success": False}), \
                mock.patch.object(tts, "_speak_offline", return_value={"success": False}):
            r = tts.speak("hi")
        self.assertFalse(r["success"])
        self.assertEqual(r["error"], "All TTS engines failed")

    def test_speak_exception_continues(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig()
        tts._lock = __import__("threading").Lock()
        tts._engines_available = {}
        with mock.patch.object(tts, "_speak_fish", side_effect=RuntimeError("boom")), \
                mock.patch.object(tts, "_speak_cosyvoice", return_value={"success": False}), \
                mock.patch.object(tts, "_speak_edge", return_value={"success": False}), \
                mock.patch.object(tts, "_speak_offline", return_value={"success": True}):
            r = tts.speak("hi")
        self.assertTrue(r["success"])
        self.assertEqual(r["engine_used"], "offline")

    def test_speak_uses_config_override(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig()
        tts._lock = __import__("threading").Lock()
        tts._engines_available = {}
        cfg = st.TTSConfig(engine="edge")
        with mock.patch.object(tts, "_speak_fish", return_value={"success": False}), \
                mock.patch.object(tts, "_speak_cosyvoice", return_value={"success": False}), \
                mock.patch.object(tts, "_speak_edge", return_value={"success": True}) as m:
            tts.speak("hi", config=cfg)
        m.assert_called_once_with("hi", cfg)

    def test_speak_fish_first(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig()
        tts._lock = __import__("threading").Lock()
        tts._engines_available = {}
        with mock.patch.object(tts, "_speak_fish", return_value={"success": True}) as m:
            r = tts.speak("hi")
        self.assertEqual(r["engine_used"], "fish")
        m.assert_called_once()


class SpeakStreamingTests(unittest.TestCase):
    def test_streaming_with_fish_key_and_httpx(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig(fish_api_key="key")
        tts._lock = __import__("threading").Lock()
        tts._engines_available = {"httpx": True}
        with mock.patch.object(tts, "_stream_fish", return_value={"success": True}) as m:
            r = tts.speak_streaming("hi")
        m.assert_called_once()

    def test_streaming_fallback_to_speak(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig(fish_api_key="")
        tts._lock = __import__("threading").Lock()
        tts._engines_available = {"httpx": False}
        with mock.patch.object(tts, "speak", return_value={"success": True}) as m:
            r = tts.speak_streaming("hi")
        m.assert_called_once()

    def test_streaming_with_config_override(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig(fish_api_key="key")
        tts._lock = __import__("threading").Lock()
        tts._engines_available = {"httpx": True}
        cfg = st.TTSConfig(fish_api_key="key2")
        with mock.patch.object(tts, "_stream_fish", return_value={"success": True}) as m:
            tts.speak_streaming("hi", on_chunk=lambda x: None, config=cfg)
        m.assert_called_once_with("hi", mock.ANY, cfg)


class SpeakFishTests(unittest.TestCase):
    def test_no_api_key(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig()
        r = tts._speak_fish("hi", st.TTSConfig())
        self.assertFalse(r["success"])
        self.assertIn("Fish Speech API key not configured", r["error"])

    def test_no_httpx(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        r = tts._speak_fish("hi", st.TTSConfig(fish_api_key="k"))
        # _HTTPX_AVAILABLE is module global; patch it
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", False):
            r = tts._speak_fish("hi", st.TTSConfig(fish_api_key="k"))
        self.assertFalse(r["success"])

    def test_success_200(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(fish_api_key="k")
        resp = mock.MagicMock(status_code=200)
        resp.content = b"audio"
        client = mock.MagicMock()
        client.__enter__ = mock.MagicMock(return_value=client)
        client.__exit__ = mock.MagicMock(return_value=False)
        client.post.return_value = resp
        httpx = mock.MagicMock()
        httpx.Client.return_value = client
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", True), \
                mock.patch.dict("sys.modules", {"httpx": httpx}):
            r = tts._speak_fish("hi", cfg)
        self.assertTrue(r["success"])
        self.assertEqual(r["audio_data"], b"audio")
        self.assertEqual(r["format"], "wav")

    def test_non_200(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(fish_api_key="k")
        resp = mock.MagicMock(status_code=400)
        resp.text = "bad request"
        client = mock.MagicMock()
        client.__enter__ = mock.MagicMock(return_value=client)
        client.__exit__ = mock.MagicMock(return_value=False)
        client.post.return_value = resp
        httpx = mock.MagicMock()
        httpx.Client.return_value = client
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", True), \
                mock.patch.dict("sys.modules", {"httpx": httpx}):
            r = tts._speak_fish("hi", cfg)
        self.assertFalse(r["success"])
        self.assertIn("Fish API 400", r["error"])

    def test_exception(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(fish_api_key="k")
        httpx = mock.MagicMock()
        httpx.Client.side_effect = Exception("net")
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", True), \
                mock.patch.dict("sys.modules", {"httpx": httpx}):
            r = tts._speak_fish("hi", cfg)
        self.assertFalse(r["success"])
        self.assertIn("net", r["error"])


class SpeakCosyvoiceTests(unittest.TestCase):
    def test_no_config(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        r = tts._speak_cosyvoice("hi", st.TTSConfig())
        self.assertFalse(r["success"])
        self.assertIn("CosyVoice API not configured", r["error"])

    def test_no_httpx(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(cosyvoice_api_url="http://x")
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", False):
            r = tts._speak_cosyvoice("hi", cfg)
        self.assertFalse(r["success"])

    def test_success_200(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(cosyvoice_api_url="http://x")
        resp = mock.MagicMock(status_code=200)
        resp.content = b"audio"
        client = mock.MagicMock()
        client.__enter__ = mock.MagicMock(return_value=client)
        client.__exit__ = mock.MagicMock(return_value=False)
        client.post.return_value = resp
        httpx = mock.MagicMock()
        httpx.Client.return_value = client
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", True), \
                mock.patch.dict("sys.modules", {"httpx": httpx}):
            r = tts._speak_cosyvoice("hi", cfg)
        self.assertTrue(r["success"])
        self.assertEqual(r["audio_data"], b"audio")

    def test_non_200(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(cosyvoice_api_url="http://x")
        resp = mock.MagicMock(status_code=500)
        client = mock.MagicMock()
        client.__enter__ = mock.MagicMock(return_value=client)
        client.__exit__ = mock.MagicMock(return_value=False)
        client.post.return_value = resp
        httpx = mock.MagicMock()
        httpx.Client.return_value = client
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", True), \
                mock.patch.dict("sys.modules", {"httpx": httpx}):
            r = tts._speak_cosyvoice("hi", cfg)
        self.assertFalse(r["success"])
        self.assertIn("CosyVoice API 500", r["error"])

    def test_exception(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(cosyvoice_api_url="http://x")
        httpx = mock.MagicMock()
        httpx.Client.side_effect = Exception("net")
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", True), \
                mock.patch.dict("sys.modules", {"httpx": httpx}):
            r = tts._speak_cosyvoice("hi", cfg)
        self.assertFalse(r["success"])
        self.assertIn("net", r["error"])


class SpeakEdgeTests(unittest.TestCase):
    def test_edge_not_available(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts._engines_available = {"edge_tts": False}
        tts.config = st.TTSConfig()
        r = tts._speak_edge("hi", st.TTSConfig())
        self.assertFalse(r["success"])
        self.assertIn("edge-tts not installed", r["error"])

    def test_edge_success(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts._engines_available = {"edge_tts": True}
        tts.config = st.TTSConfig()
        with mock.patch("asyncio.run", return_value=b"audio"), \
                mock.patch.dict("sys.modules", {"edge_tts": mock.MagicMock()}):
            r = tts._speak_edge("hi", st.TTSConfig(speed=1.2))
        self.assertTrue(r["success"])
        self.assertEqual(r["audio_data"], b"audio")
        self.assertEqual(r["format"], "mp3")

    def test_edge_speed_less_than_1(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts._engines_available = {"edge_tts": True}
        tts.config = st.TTSConfig()
        with mock.patch("asyncio.run", return_value=b"audio") as ar, \
                mock.patch.dict("sys.modules", {"edge_tts": mock.MagicMock()}):
            tts._speak_edge("hi", st.TTSConfig(speed=0.5))
        # rate computed; just ensure called
        ar.assert_called_once()

    def test_edge_no_audio(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts._engines_available = {"edge_tts": True}
        tts.config = st.TTSConfig()
        with mock.patch("asyncio.run", return_value=b""), \
                mock.patch.dict("sys.modules", {"edge_tts": mock.MagicMock()}):
            r = tts._speak_edge("hi", st.TTSConfig())
        self.assertFalse(r["success"])
        self.assertIn("No audio data", r["error"])

    def test_edge_exception(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts._engines_available = {"edge_tts": True}
        tts.config = st.TTSConfig()
        with mock.patch("asyncio.run", side_effect=Exception("boom")), \
                mock.patch.dict("sys.modules", {"edge_tts": mock.MagicMock()}):
            r = tts._speak_edge("hi", st.TTSConfig())
        self.assertFalse(r["success"])
        self.assertIn("boom", r["error"])


class EdgeStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_edge_stream(self):
        import edge_tts
        edge_tts_mod = mock.MagicMock()

        async def fake_stream():
            yield {"type": "audio", "data": b"chunk1"}
            yield {"type": "text", "data": b"ignored"}
            yield {"type": "audio", "data": b"chunk2"}

        comm = mock.MagicMock()
        comm.stream = fake_stream
        edge_tts_mod.Communicate.return_value = comm
        with mock.patch.dict("sys.modules", {"edge_tts": edge_tts_mod}):
            tts = st.StreamingTTS.__new__(st.StreamingTTS)
            audio = await tts._edge_stream("hi", "voice", "+10%")
        self.assertEqual(audio, b"chunk1chunk2")
        edge_tts_mod.Communicate.assert_called_once_with("hi", voice="voice", rate="+10%")


class SpeakOfflineTests(unittest.TestCase):
    def test_offline_success(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig()
        engine = mock.MagicMock()
        pyttsx3 = mock.MagicMock()
        pyttsx3.init.return_value = engine
        with mock.patch.dict("sys.modules", {"pyttsx3": pyttsx3}):
            r = tts._speak_offline("hi", st.TTSConfig())
        self.assertTrue(r["success"])
        self.assertEqual(r["format"], "none")
        self.assertEqual(r["engine_used"], "pyttsx3")
        engine.say.assert_called_once_with("hi")
        engine.runAndWait.assert_called_once()

    def test_offline_exception(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig()
        pyttsx3 = mock.MagicMock()
        pyttsx3.init.side_effect = Exception("no engine")
        with mock.patch.dict("sys.modules", {"pyttsx3": pyttsx3}):
            r = tts._speak_offline("hi", st.TTSConfig())
        self.assertFalse(r["success"])
        self.assertIn("no engine", r["error"])


class StreamFishTests(unittest.TestCase):
    def test_no_key_falls_back_to_speak(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig(fish_api_key="")
        with mock.patch.object(tts, "speak", return_value={"success": True}) as m:
            r = tts._stream_fish("hi", None, st.TTSConfig())
        m.assert_called_once()

    def test_no_httpx_falls_back(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", False), \
                mock.patch.object(tts, "speak", return_value={"success": True}) as m:
            r = tts._stream_fish("hi", None, st.TTSConfig(fish_api_key="k"))
        m.assert_called_once()

    def test_success_streams(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(fish_api_key="k")
        chunks = [b"chunk1", b"chunk2"]
        resp = mock.MagicMock()
        resp.status_code = 200

        def iter_bytes(chunk_size=4096):
            for c in chunks:
                yield c
        resp.iter_bytes = iter_bytes
        stream_cm = mock.MagicMock()
        stream_cm.__enter__ = mock.MagicMock(return_value=resp)
        stream_cm.__exit__ = mock.MagicMock(return_value=False)
        client = mock.MagicMock()
        client.stream.return_value = stream_cm
        client.__enter__ = mock.MagicMock(return_value=client)
        client.__exit__ = mock.MagicMock(return_value=False)
        httpx = mock.MagicMock()
        httpx.Client.return_value = client
        on_chunk = mock.MagicMock()
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", True), \
                mock.patch.dict("sys.modules", {"httpx": httpx}):
            r = tts._stream_fish("hi", on_chunk, cfg)
        self.assertTrue(r["success"])
        self.assertEqual(r["audio_data"], b"chunk1chunk2")
        self.assertTrue(r["streamed"])
        self.assertEqual(on_chunk.call_count, 2)

    def test_non_200(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(fish_api_key="k")
        resp = mock.MagicMock(status_code=400)
        stream_cm = mock.MagicMock()
        stream_cm.__enter__ = mock.MagicMock(return_value=resp)
        stream_cm.__exit__ = mock.MagicMock(return_value=False)
        client = mock.MagicMock()
        client.stream.return_value = stream_cm
        client.__enter__ = mock.MagicMock(return_value=client)
        client.__exit__ = mock.MagicMock(return_value=False)
        httpx = mock.MagicMock()
        httpx.Client.return_value = client
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", True), \
                mock.patch.dict("sys.modules", {"httpx": httpx}):
            r = tts._stream_fish("hi", None, cfg)
        self.assertFalse(r["success"])
        self.assertIn("Fish streaming failed", r["error"])

    def test_exception(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(fish_api_key="k")
        httpx = mock.MagicMock()
        httpx.Client.side_effect = Exception("net")
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", True), \
                mock.patch.dict("sys.modules", {"httpx": httpx}):
            r = tts._stream_fish("hi", None, cfg)
        self.assertFalse(r["success"])
        self.assertIn("net", r["error"])

    def test_on_chunk_none(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        cfg = st.TTSConfig(fish_api_key="k")
        chunks = [b"c1"]
        resp = mock.MagicMock()
        resp.status_code = 200

        def iter_bytes(chunk_size=4096):
            for c in chunks:
                yield c
        resp.iter_bytes = iter_bytes
        stream_cm = mock.MagicMock()
        stream_cm.__enter__ = mock.MagicMock(return_value=resp)
        stream_cm.__exit__ = mock.MagicMock(return_value=False)
        client = mock.MagicMock()
        client.stream.return_value = stream_cm
        client.__enter__ = mock.MagicMock(return_value=client)
        client.__exit__ = mock.MagicMock(return_value=False)
        httpx = mock.MagicMock()
        httpx.Client.return_value = client
        with mock.patch("orbit.orbit.streaming_tts._HTTPX_AVAILABLE", True), \
                mock.patch.dict("sys.modules", {"httpx": httpx}):
            r = tts._stream_fish("hi", None, cfg)
        self.assertTrue(r["success"])


class ListEnginesSetConfigTests(unittest.TestCase):
    def test_list_engines(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts._engines_available = {"a": True, "b": False}
        tts.config = st.TTSConfig()
        self.assertEqual(tts.list_engines(), {"a": True, "b": False})

    def test_set_config(self):
        tts = st.StreamingTTS.__new__(st.StreamingTTS)
        tts.config = st.TTSConfig()
        tts.set_config(speed=1.5, voice="v", unknown="x")
        self.assertEqual(tts.config.speed, 1.5)
        self.assertEqual(tts.config.voice, "v")
        self.assertFalse(hasattr(tts.config, "unknown"))


class ModuleLevelTests(unittest.TestCase):
    def test_speak_module(self):
        with mock.patch("orbit.orbit.streaming_tts.get_streaming_tts") as g:
            tts = mock.MagicMock()
            tts.speak.return_value = {"ok": True}
            g.return_value = tts
            r = st.speak("hi", speed=1.2)
        self.assertEqual(r, {"ok": True})
        tts.speak.assert_called_once_with("hi", speed=1.2)

    def test_speak_streaming_module(self):
        with mock.patch("orbit.orbit.streaming_tts.get_streaming_tts") as g:
            tts = mock.MagicMock()
            tts.speak_streaming.return_value = {"ok": True}
            g.return_value = tts
            r = st.speak_streaming("hi", on_chunk=lambda x: None)
        self.assertEqual(r, {"ok": True})

    def test_get_streaming_tts_singleton(self):
        st._streaming_tts = None
        with mock.patch("orbit.orbit.streaming_tts.StreamingTTS",
                        return_value=mock.MagicMock()) as C:
            a = st.get_streaming_tts()
            b = st.get_streaming_tts()
        self.assertIs(a, b)
        C.assert_called_once()
        st._streaming_tts = None


if __name__ == "__main__":
    unittest.main()
