"""Deep tests for orbit/orbit/music_ctrl.py (Loop 14/3)."""

import ctypes
import platform
import subprocess
import threading
import unittest
from unittest import mock

from orbit.orbit import music_ctrl as mc


class SendVkTests(unittest.TestCase):
    def test_non_windows_returns_false(self):
        with mock.patch.object(mc, "_is_windows", False):
            self.assertFalse(mc._send_vk(0xB3))

    def test_windows_success(self):
        user32 = mock.MagicMock()
        with mock.patch.object(mc, "_is_windows", True), \
                mock.patch.object(mc.ctypes, "windll", create=True) as windll:
            windll.user32 = user32
            self.assertTrue(mc._send_vk(0xB3))
        self.assertEqual(user32.keybd_event.call_count, 2)

    def test_windows_exception_returns_false(self):
        with mock.patch.object(mc, "_is_windows", True), \
                mock.patch.object(mc.ctypes, "windll", create=True) as windll:
            windll.user32.keybd_event.side_effect = Exception("boom")
            self.assertFalse(mc._send_vk(0xB3))


class PowershellTests(unittest.TestCase):
    def test_success(self):
        r = mock.MagicMock(stdout="  hello  ", returncode=0)
        with mock.patch("subprocess.run", return_value=r):
            self.assertEqual(mc._powershell("cmd"), "hello")

    def test_exception_returns_none(self):
        with mock.patch("subprocess.run", side_effect=Exception("boom")):
            self.assertIsNone(mc._powershell("cmd"))


class SimpleActionTests(unittest.TestCase):
    def test_play_pause(self):
        with mock.patch.object(mc, "_send_vk", return_value=True) as svk:
            self.assertTrue(mc.play_pause())
        svk.assert_called_once_with(mc.VK_MEDIA_PLAY_PAUSE)

    def test_next_track(self):
        with mock.patch.object(mc, "_send_vk", return_value=False) as svk:
            self.assertFalse(mc.next_track())
        svk.assert_called_once_with(mc.VK_MEDIA_NEXT_TRACK)

    def test_prev_track(self):
        with mock.patch.object(mc, "_send_vk", return_value=True) as svk:
            self.assertTrue(mc.prev_track())
        svk.assert_called_once_with(mc.VK_MEDIA_PREV_TRACK)

    def test_stop(self):
        with mock.patch.object(mc, "_send_vk", return_value=True) as svk:
            self.assertTrue(mc.stop())
        svk.assert_called_once_with(mc.VK_MEDIA_STOP)

    def test_mute(self):
        with mock.patch.object(mc, "_send_vk", return_value=True) as svk:
            self.assertTrue(mc.mute())
        svk.assert_called_once_with(mc.VK_VOLUME_MUTE)

    def test_volume_up(self):
        with mock.patch.object(mc, "_send_vk", return_value=True) as svk:
            mc.volume_up(3)
        self.assertEqual(svk.call_count, 3)
        svk.assert_called_with(mc.VK_VOLUME_UP)

    def test_volume_up_default(self):
        with mock.patch.object(mc, "_send_vk", return_value=True) as svk:
            mc.volume_up()
        self.assertEqual(svk.call_count, 2)

    def test_volume_down(self):
        with mock.patch.object(mc, "_send_vk", return_value=True) as svk:
            mc.volume_down(1)
        self.assertEqual(svk.call_count, 1)
        svk.assert_called_with(mc.VK_VOLUME_DOWN)


class SetVolumeTests(unittest.TestCase):
    def setUp(self):
        # reset global _volume
        with mc._volume_lock:
            mc._volume = 50
        self.addCleanup(self._restore)

    def _restore(self):
        with mc._volume_lock:
            mc._volume = 50

    def test_clamp_low(self):
        with mock.patch.object(mc, "volume_up"), mock.patch.object(mc, "volume_down"):
            mc.set_volume(-10)
        with mc._volume_lock:
            self.assertEqual(mc._volume, 0)

    def test_clamp_high(self):
        with mock.patch.object(mc, "volume_up"), mock.patch.object(mc, "volume_down"):
            mc.set_volume(200)
        with mc._volume_lock:
            self.assertEqual(mc._volume, 100)

    def test_increase_calls_volume_up(self):
        with mock.patch.object(mc, "volume_up") as vu, \
                mock.patch.object(mc, "volume_down") as vd:
            mc.set_volume(70)
        vu.assert_called_once()
        vd.assert_not_called()
        with mc._volume_lock:
            self.assertEqual(mc._volume, 70)

    def test_decrease_calls_volume_down(self):
        with mock.patch.object(mc, "volume_up") as vu, \
                mock.patch.object(mc, "volume_down") as vd:
            mc.set_volume(30)
        vd.assert_called_once()
        vu.assert_not_called()
        with mc._volume_lock:
            self.assertEqual(mc._volume, 30)

    def test_equal_no_volume_call(self):
        # diff = 0 -> else branch (volume_down with abs(0)//2+1 = 1)?? 
        # code: if diff > 0: volume_up else: volume_down(abs(diff)//2+1)
        # diff=0 -> else -> volume_down(1)
        with mock.patch.object(mc, "volume_up") as vu, \
                mock.patch.object(mc, "volume_down") as vd:
            mc.set_volume(50)
        vd.assert_called_once()
        vu.assert_not_called()


class GetVolumeTests(unittest.TestCase):
    def setUp(self):
        with mc._volume_lock:
            mc._volume = 50
        self.addCleanup(self._restore)

    def _restore(self):
        with mc._volume_lock:
            mc._volume = 50

    def test_non_windows_returns_volume(self):
        with mock.patch.object(mc, "_is_windows", False):
            self.assertEqual(mc.get_volume(), 50)

    def test_windows_win32api_available_returns_50(self):
        with mock.patch.object(mc, "_is_windows", True), \
                mock.patch("builtins.__import__", side_effect=lambda name, *a, **k: __import__(name, *a, **k) if name != "win32api" else mock.MagicMock()):
            # win32api importable -> returns 50
            self.assertEqual(mc.get_volume(), 50)

    def test_windows_no_win32api_calls_powershell(self):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "win32api":
                raise ImportError("no win32api")
            return real_import(name, *a, **k)

        with mock.patch.object(mc, "_is_windows", True), \
                mock.patch("builtins.__import__", side_effect=fake_import), \
                mock.patch.object(mc, "_powershell", return_value="") as ps:
            self.assertEqual(mc.get_volume(), 50)
        ps.assert_called_once()

    def test_windows_powershell_exception_logged(self):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "win32api":
                raise ImportError("no win32api")
            return real_import(name, *a, **k)

        with mock.patch.object(mc, "_is_windows", True), \
                mock.patch("builtins.__import__", side_effect=fake_import), \
                mock.patch.object(mc, "_powershell", side_effect=Exception("boom")), \
                mock.patch.object(mc, "logger") as lg:
            self.assertEqual(mc.get_volume(), 50)
        lg.exception.assert_called_once()


class IsPlayingTests(unittest.TestCase):
    def test_returns_none(self):
        self.assertIsNone(mc.is_playing())


class ParseTextTests(unittest.TestCase):
    def _patch_vk(self):
        return mock.patch.object(mc, "_send_vk", return_value=True)

    def test_pause(self):
        with mock.patch.object(mc, "stop", return_value=True) as st:
            r = mc.parse_text("stop music")
        st.assert_called_once()
        self.assertEqual(r, {"type": "action", "result": "⏸️ Paused", "action": "pause"})

    def test_pause_via_play_pause(self):
        with mock.patch.object(mc, "stop", return_value=False), \
                mock.patch.object(mc, "play_pause", return_value=True) as pp:
            r = mc.parse_text("pause")
        pp.assert_called_once()
        self.assertEqual(r["result"], "⏸️ Paused")

    def test_play(self):
        with mock.patch.object(mc, "play_pause", return_value=True) as pp:
            r = mc.parse_text("play song")
        pp.assert_called_once()
        self.assertEqual(r, {"type": "action", "result": "▶️ Play", "action": "play"})

    def test_play_fail(self):
        with mock.patch.object(mc, "play_pause", return_value=False):
            r = mc.parse_text("chala")
        self.assertEqual(r["result"], "❌ Play nahi kar paya")

    def test_next(self):
        with mock.patch.object(mc, "next_track", return_value=True) as nt:
            r = mc.parse_text("next track")
        nt.assert_called_once()
        self.assertEqual(r, {"type": "action", "result": "⏭️ Next track", "action": "next"})

    def test_next_fail(self):
        with mock.patch.object(mc, "next_track", return_value=False):
            r = mc.parse_text("agla")
        self.assertEqual(r["result"], "❌ Skip nahi kar paya")

    def test_prev(self):
        with mock.patch.object(mc, "prev_track", return_value=True) as pt:
            r = mc.parse_text("previous")
        pt.assert_called_once()
        self.assertEqual(r, {"type": "action", "result": "⏮️ Previous track", "action": "prev"})

    def test_prev_fail(self):
        with mock.patch.object(mc, "prev_track", return_value=False):
            r = mc.parse_text("pichla")
        self.assertEqual(r["result"], "❌ Previous nahi kar paya")

    def test_mute(self):
        with mock.patch.object(mc, "mute", return_value=True) as m:
            r = mc.parse_text("mute")
        m.assert_called_once()
        self.assertEqual(r, {"type": "action", "result": "🔇 Muted!", "action": "mute"})

    def test_mute_fail(self):
        with mock.patch.object(mc, "mute", return_value=False):
            r = mc.parse_text("chup")
        self.assertEqual(r["result"], "❌ Mute nahi kar paya")

    def test_volume_number(self):
        with mock.patch.object(mc, "set_volume") as sv:
            r = mc.parse_text("volume 42")
        sv.assert_called_once_with(42)
        self.assertEqual(r, {"type": "action", "result": "🔊 Volume set to 42%",
                             "action": "volume", "level": 42})

    def test_volume_up(self):
        with mock.patch.object(mc, "volume_up") as vu:
            r = mc.parse_text("volume up")
        vu.assert_called_once()
        self.assertEqual(r, {"type": "action", "result": "🔊 Volume up!",
                             "action": "volume_up"})

    def test_volume_up_badhao(self):
        with mock.patch.object(mc, "volume_up") as vu:
            r = mc.parse_text("badhao")
        vu.assert_called_once()

    def test_volume_down(self):
        with mock.patch.object(mc, "volume_down") as vd:
            r = mc.parse_text("volume down")
        vd.assert_called_once()
        self.assertEqual(r, {"type": "action", "result": "🔉 Volume down!",
                             "action": "volume_down"})

    def test_volume_down_kam(self):
        with mock.patch.object(mc, "volume_down") as vd:
            r = mc.parse_text("kam kar")
        vd.assert_called_once()

    def test_unknown(self):
        r = mc.parse_text("blah blah")
        self.assertEqual(r["type"], "info")
        self.assertIn("Kya karna hai", r["result"])

    def test_pause_checked_before_play(self):
        # "display volume" contains "play" substring but pause/stop keyword present
        with mock.patch.object(mc, "stop", return_value=True) as st, \
                mock.patch.object(mc, "play_pause") as pp:
            r = mc.parse_text("stop display")
        st.assert_called_once()
        pp.assert_not_called()

    def test_play_keyword_chala(self):
        with mock.patch.object(mc, "play_pause", return_value=True):
            r = mc.parse_text("chala de")
        self.assertEqual(r["action"], "play")

    def test_skip_keyword(self):
        with mock.patch.object(mc, "next_track", return_value=True):
            r = mc.parse_text("skip this")
        self.assertEqual(r["action"], "next")

    def test_wapis_keyword(self):
        with mock.patch.object(mc, "prev_track", return_value=True):
            r = mc.parse_text("wapis")
        self.assertEqual(r["action"], "prev")

    def test_silent_keyword(self):
        with mock.patch.object(mc, "mute", return_value=True):
            r = mc.parse_text("silent mode")
        self.assertEqual(r["action"], "mute")

    def test_zyada_keyword(self):
        with mock.patch.object(mc, "volume_up") as vu:
            r = mc.parse_text("zyada kar")
        vu.assert_called_once()

    def test_dheema_keyword(self):
        with mock.patch.object(mc, "volume_down") as vd:
            r = mc.parse_text("dheema kar")
        vd.assert_called_once()

    def test_te_z_keyword(self):
        with mock.patch.object(mc, "volume_up") as vu:
            r = mc.parse_text("tez kar")
        vu.assert_called_once()

    def test_aage_keyword(self):
        with mock.patch.object(mc, "next_track", return_value=True):
            r = mc.parse_text("aage")
        self.assertEqual(r["action"], "next")

    def test_piche_keyword(self):
        with mock.patch.object(mc, "prev_track", return_value=True):
            r = mc.parse_text("piche")
        self.assertEqual(r["action"], "prev")

    def test_ruko_keyword(self):
        with mock.patch.object(mc, "play_pause", return_value=True):
            r = mc.parse_text("ruko")
        # ruko -> pause branch: stop() if _w("stop") else play_pause()
        # _w("stop") False -> play_pause
        self.assertEqual(r["action"], "pause")

    def test_tham_keyword(self):
        with mock.patch.object(mc, "play_pause", return_value=True):
            r = mc.parse_text("tham")
        self.assertEqual(r["action"], "pause")


if __name__ == "__main__":
    unittest.main()
