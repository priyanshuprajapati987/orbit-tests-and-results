"""Deep tests for orbit/launch_desktop.py — the PyQt5 desktop shell (1098 lines).

Covers:
- module constants / _env_port env parsing
- SplashOverlay: start() state, _adv phase machine, _tick ring wrap, paintEvent
  (particles/rings/orbit-dots/logo/text/progress-bar/phase labels) via grab()
- TitleBar: connected state, window buttons, drag/move/double-click
- AgentCard / Sidebar / StatusBar behaviour
- orbitWindow: web view wiring, JS dispatchers, maximize/close/tray/shortcuts
- run_startup_sequence (skip values, import failure, progress callback)
- start_server / wait_server / main() (early exit + full GUI flow with fakes)
"""

import io
import os
import sys
import time
import types
import unittest
import urllib.error
from contextlib import redirect_stdout
from unittest import mock

from PyQt5.QtCore import QEvent, QEventLoop, QPoint, QPointF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCloseEvent, QKeySequence, QMouseEvent
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QShortcut,
    QSystemTrayIcon,
)

import orbit.launch_desktop as ld

# One QApplication for the whole module (widgets need it; second instance would raise).
_APP = QApplication.instance() or QApplication(sys.argv)


def _drain(ms=200):
    """Run the Qt event loop for `ms` then return the exit code for main()."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()
    return 0


class _FakeWeb(QLabel):
    """QWidget stand-in for QWebEngineView: page() is a mock, load() emits
    loadFinished synchronously so main()'s on_loaded path runs."""

    loadFinished = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = mock.MagicMock()
        self.loaded_urls = []

    def page(self):
        return self._page

    def load(self, url):
        self.loaded_urls.append(url)
        self.loadFinished.emit(True)

    def reload(self):
        pass

    def stop(self):
        pass


class _AutoSplash(ld.SplashOverlay):
    """Splash that fires `finished` on the next event-loop tick so main()'s
    on_splash_done closure runs without waiting for the full animation."""

    def start(self):
        super().start()
        QTimer.singleShot(0, self.finished.emit)


class _BrokenSettingsWeb(_FakeWeb):
    """page().settings()/profile() raise -> main()'s try/except pass branches."""

    def page(self):
        page = super().page()
        page.settings.side_effect = RuntimeError("settings unavailable")
        page.profile.side_effect = RuntimeError("profile unavailable")
        return page


class TestConstantsAndEnv(unittest.TestCase):
    def test_host_and_port(self):
        self.assertEqual(ld.HOST, "127.0.0.1")
        self.assertIsInstance(ld.PORT, int)
        self.assertEqual(ld.PORT, ld._env_port())

    def test_env_port_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORBIT_PORT", None)
            self.assertEqual(ld._env_port(), 5000)

    def test_env_port_valid(self):
        with mock.patch.dict(os.environ, {"ORBIT_PORT": "8123"}):
            self.assertEqual(ld._env_port(), 8123)

    def test_env_port_invalid(self):
        for bad in ("", "abc", "99.5", "None"):
            with self.subTest(bad=bad), mock.patch.dict(os.environ, {"ORBIT_PORT": bad}):
                self.assertEqual(ld._env_port(), 5000)

    def test_color_palette_keys(self):
        for key in ("bg", "surface", "border", "text", "accent", "success", "danger", "info"):
            self.assertIn(key, ld.C)
            self.assertTrue(ld.C[key].startswith("#"))

    def test_agents_table(self):
        self.assertEqual(len(ld.AGENTS), 21)
        ids = [a[0] for a in ld.AGENTS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ld.AGENTS[0], ("QUEEN", "Queen", "Orchestrator", ld.C["warning"]))
        for entry in ld.AGENTS:
            self.assertEqual(len(entry), 4)
            self.assertTrue(entry[3].startswith("#"))

    def test_webengine_flags_set(self):
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        self.assertIn("swiftshader", flags)
        self.assertIn("--in-process-gpu", flags)
        self.assertNotIn("--disable-gpu", flags)

    def test_webengine_detected(self):
        self.assertIsInstance(ld.WEBENGINE, bool)


class TestSplashOverlay(unittest.TestCase):
    def setUp(self):
        self.win = ld.orbitWindow()  # hidden parent keeps the splash off-screen
        self.addCleanup(self.win.deleteLater)
        self.sp = ld.SplashOverlay(self.win)
        self.sp.resize(480, 360)
        self.addCleanup(self.sp.deleteLater)

    def test_start_initializes_animation_state(self):
        self.sp.start()
        self.assertEqual(self.sp._phase, 1)
        self.assertEqual(self.sp._p, 0)
        self.assertEqual(len(self.sp._particles), 50)
        for particle in self.sp._particles:
            self.assertEqual(len(particle), 7)  # x, y, vx, vy, size, alpha, color
        self.assertEqual(len(self.sp._rings), 3)
        self.assertEqual(len(self.sp._orbit_dots), 8)
        for dot in self.sp._orbit_dots:
            self.assertEqual(len(dot), 4)
        self.assertTrue(self.sp._t1.isActive())
        self.assertTrue(self.sp._t2.isActive())
        self.assertFalse(self.sp.isHidden())  # start() called show()
        self.sp._t1.stop()
        self.sp._t2.stop()

    def test_adv_phase1_progression(self):
        self.sp._phase, self.sp._t, self.sp._p = 1, 0, 0.0
        self.sp._logo_scale = self.sp._text_alpha = 0.0
        self.sp._shimmer = self.sp._pulse = 0.0

        self.sp._adv()  # tick 1: plain growth
        self.assertEqual(self.sp._t, 1)
        self.assertAlmostEqual(self.sp._p, 0.8)
        self.assertAlmostEqual(self.sp._logo_scale, 0.03)
        self.assertEqual(self.sp._text_alpha, 0.0)
        self.assertEqual(self.sp._shimmer, 0.0)
        self.assertEqual(self.sp._pulse, 0.0)

        self.sp._t = 20
        self.sp._adv()  # tick 21: text alpha starts
        self.assertEqual(self.sp._t, 21)
        self.assertAlmostEqual(self.sp._text_alpha, 0.025)
        self.assertEqual(self.sp._shimmer, 0.0)

        self.sp._t = 30
        self.sp._adv()  # tick 31: pulse starts
        self.assertAlmostEqual(self.sp._pulse, 0.02)

        self.sp._t = 50
        self.sp._adv()  # tick 51: shimmer starts
        self.assertAlmostEqual(self.sp._shimmer, 0.015)

    def test_adv_caps_progress_and_switches_phase(self):
        # Patch QTimer: a real singleShot(500) would fire later, inside some
        # other test's event loop, and touch this (then deleted) splash.
        with mock.patch.object(ld, "QTimer") as qt:
            self.sp._phase, self.sp._t, self.sp._p = 1, 0, 99.6
            self.sp._adv()
            self.assertEqual(self.sp._phase, 2)
            self.assertGreaterEqual(self.sp._p, 100)
            qt.singleShot.assert_called_once()  # completion scheduled with 500ms
            self.assertEqual(qt.singleShot.call_args[0][0], 500)

    def test_adv_phase2_decays_progress(self):
        self.sp._phase, self.sp._p = 2, 50
        self.sp._adv()
        self.assertEqual(self.sp._p, 47)

    def test_finished_signal_fires_and_stops_timers(self):
        done = []
        loop = QEventLoop()
        safety = QTimer()
        safety.setSingleShot(True)
        safety.timeout.connect(loop.quit)
        safety.start(2500)
        self.sp.finished.connect(lambda: (done.append(True), loop.quit()))
        self.sp.start()
        self.sp._p = 100
        self.sp._adv()  # schedules the 500ms singleShot completion
        loop.exec_()
        self.assertEqual(done, [True])
        self.assertEqual(self.sp._phase, 2)
        self.assertFalse(self.sp._t1.isActive())
        self.assertFalse(self.sp._t2.isActive())

    def test_tick_wraps_ring_angles(self):
        self.sp._ring, self.sp._ring2, self.sp._ring3, self.sp._wave = 359, 1, 359.5, 358
        self.sp._tick()
        self.assertEqual(self.sp._ring, 1)
        self.assertEqual(self.sp._ring2, 359.5)  # 1 - 1.5 -> -0.5 % 360
        self.assertAlmostEqual(self.sp._ring3, 0.3)  # float: 360.3 % 360
        self.assertEqual(self.sp._wave, 2)


class TestSplashPaint(unittest.TestCase):
    """Drive paintEvent through grab() with different animation states."""

    def setUp(self):
        self.sp = ld.SplashOverlay()
        self.sp.resize(480, 360)
        self.addCleanup(self.sp.deleteLater)
        # deterministic scene instead of start() (avoids timers)
        self.sp._particles = [(10, 20, 0.2, -0.4, 3.0, 0.4, "#8b5cf6")]
        self.sp._rings = [(0, 0, 62, 0.02, 2), (0, 0, 78, -0.015, 1.5), (0, 0, 94, 0.01, 1)]
        self.sp._orbit_dots = [(0.5, 70, 0.4, "#22d3ee")]

    def _render(self, **state):
        for key, value in state.items():
            setattr(self.sp, key, value)
        pixmap = self.sp.grab()
        self.assertFalse(pixmap.isNull())
        return pixmap

    def test_paint_minimal_state(self):
        self._render(_phase=1, _p=0, _logo_scale=0, _text_alpha=0)

    def test_paint_full_state(self):
        self._render(
            _phase=1, _p=60, _logo_scale=1.0, _text_alpha=1.0,
            _shimmer=1.0, _pulse=1.0, _t=0,
        )

    def test_paint_phase2_fade(self):
        self._render(_phase=2, _t=10, _p=80, _logo_scale=1.0, _text_alpha=1.0)

    def test_paint_phase_labels(self):
        cases = [
            (10, "Booting systems..."),
            (30, "Loading intelligence..."),
            (50, "Initializing neural mesh..."),
            (70, "Activating agents..."),
            (99, "Ready!"),  # for/else: no threshold matched
        ]
        for progress, label in cases:
            with self.subTest(progress=progress):
                pixmap = self._render(
                    _phase=1, _t=0, _p=progress, _logo_scale=0, _text_alpha=0
                )
                self.assertFalse(pixmap.isNull())

    def test_paint_particles_trail_branch(self):
        with mock.patch.object(ld.random, "random", return_value=0.01):  # < 0.03
            self._render(_phase=1, _p=60, _logo_scale=1.0, _text_alpha=1.0)
        with mock.patch.object(ld.random, "random", return_value=0.5):  # no trail
            self._render(_phase=1, _p=60, _logo_scale=1.0, _text_alpha=1.0)


class TestTitleBar(unittest.TestCase):
    def setUp(self):
        self.tb = ld.TitleBar()
        self.tb.move(0, 0)  # deterministic drag arithmetic
        self.addCleanup(self.tb.deleteLater)

    def test_widgets_created(self):
        self.assertEqual(self.tb.height(), 38)
        self.assertEqual(self.tb.status_text.text(), "Connected")
        self.assertTrue(self.tb.status_dot.styleSheet().startswith("background:"))
        buttons = self.tb.findChildren(QPushButton)
        self.assertEqual(len(buttons), 3)
        self.assertEqual([b.text() for b in buttons], ["\u2014", "\u25a1", "\u2715"])

    def test_set_connected_states(self):
        self.tb.set_connected(True)
        self.assertEqual(self.tb.status_text.text(), "Connected")
        self.assertIn(ld.C["success"], self.tb.status_text.styleSheet())
        self.assertIn(ld.C["success"], self.tb.status_dot.styleSheet())

        self.tb.set_connected(False)
        self.assertEqual(self.tb.status_text.text(), "Disconnected")
        self.assertIn(ld.C["danger"], self.tb.status_text.styleSheet())
        self.assertIn(ld.C["danger"], self.tb.status_dot.styleSheet())

    def test_window_buttons_emit_signals(self):
        hits = []
        self.tb.minimize_clicked.connect(lambda: hits.append("min"))
        self.tb.maximize_clicked.connect(lambda: hits.append("max"))
        self.tb.close_clicked.connect(lambda: hits.append("close"))
        for button in self.tb.findChildren(QPushButton):
            button.click()
        self.assertEqual(hits, ["min", "max", "close"])

    def test_close_button_hover_style_is_red(self):
        close_btn = self.tb.findChildren(QPushButton)[-1]
        self.assertIn("#ef4444", close_btn.styleSheet())

    def test_mouse_drag_moves_window(self):
        press = QMouseEvent(
            QEvent.MouseButtonPress, QPointF(5, 5), QPointF(100, 100),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
        )
        self.tb.mousePressEvent(press)
        self.assertEqual(self.tb._drag, QPoint(100, 100))

        move = QMouseEvent(
            QEvent.MouseMove, QPointF(5, 5), QPointF(150, 120),
            Qt.NoButton, Qt.LeftButton, Qt.NoModifier,
        )
        self.tb.mouseMoveEvent(move)
        self.assertEqual(self.tb.window().pos(), QPoint(50, 20))

        release = QMouseEvent(
            QEvent.MouseButtonRelease, QPointF(5, 5), QPointF(150, 120),
            Qt.LeftButton, Qt.NoButton, Qt.NoModifier,
        )
        self.tb.mouseReleaseEvent(release)
        self.assertIsNone(self.tb._drag)

    def test_mouse_move_without_drag_is_noop(self):
        before = self.tb.window().pos()
        move = QMouseEvent(
            QEvent.MouseMove, QPointF(5, 5), QPointF(400, 400),
            Qt.NoButton, Qt.LeftButton, Qt.NoModifier,
        )
        self.tb.mouseMoveEvent(move)
        self.assertEqual(self.tb.window().pos(), before)

    def test_double_click_maximizes(self):
        hits = []
        self.tb.maximize_clicked.connect(lambda: hits.append(1))
        dbl = QMouseEvent(
            QEvent.MouseButtonDblClick, QPointF(5, 5), QPointF(50, 50),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
        )
        self.tb.mouseDoubleClickEvent(dbl)
        self.assertEqual(hits, [1])


class TestAgentCard(unittest.TestCase):
    def setUp(self):
        self.card = ld.AgentCard("PLN", "Planner", "Planning", ld.C["info"])
        self.addCleanup(self.card.deleteLater)

    def test_init(self):
        self.assertEqual(self.card.agent_id, "PLN")
        self.assertFalse(self.card._active)
        self.assertEqual(self.card.height(), 34)
        labels = [l.text() for l in self.card.findChildren(QLabel)]
        self.assertIn("PLN", labels)
        self.assertIn("Planner", labels)
        self.assertIn("Planning", labels)

    def test_set_active_styling(self):
        self.card.set_active(True)
        self.assertTrue(self.card._active)
        self.assertIn("border-left", self.card.styleSheet())
        self.assertIn("font-weight:bold", self.card.nm.styleSheet())
        self.assertIn(ld.C["info"], self.card.nm.styleSheet())

        self.card.set_active(False)
        self.assertFalse(self.card._active)
        self.assertEqual(self.card.styleSheet(), "")
        self.assertNotIn("font-weight:bold", self.card.nm.styleSheet())

    def test_hover_when_inactive(self):
        self.card.enterEvent(None)
        self.assertIn(ld.C["border"], self.card.styleSheet())
        self.card.leaveEvent(None)
        self.assertEqual(self.card.styleSheet(), "")

    def test_hover_ignored_when_active(self):
        self.card.set_active(True)
        active_style = self.card.styleSheet()
        self.card.enterEvent(None)
        self.assertEqual(self.card.styleSheet(), active_style)
        self.card.leaveEvent(None)
        self.assertEqual(self.card.styleSheet(), active_style)


class TestSidebar(unittest.TestCase):
    def setUp(self):
        self.sb = ld.Sidebar()
        self.addCleanup(self.sb.deleteLater)

    def test_structure(self):
        self.assertEqual(self.sb.width(), 220)
        self.assertEqual(len(self.sb._cards), len(ld.AGENTS))
        labels = [l.text() for l in self.sb.findChildren(QLabel)]
        self.assertIn("AGENTS", labels)
        self.assertIn(str(len(ld.AGENTS)), labels)
        self.assertIn("QUICK ACTIONS", labels)
        for signal_name in (
            "agent_selected", "clear_chat", "toggle_dashboard", "toggle_settings",
            "toggle_permissions", "toggle_3d_core", "panel_selected", "show_web",
        ):
            self.assertTrue(hasattr(self.sb, signal_name))

    def test_select_activates_single_card_and_emits(self):
        hits = []
        self.sb.agent_selected.connect(hits.append)
        self.sb._sel("QUEEN")
        active = [c.agent_id for c in self.sb._cards if c._active]
        self.assertEqual(active, ["QUEEN"])
        self.assertEqual(hits, ["QUEEN"])

        self.sb._sel("SEC")
        active = [c.agent_id for c in self.sb._cards if c._active]
        self.assertEqual(active, ["SEC"])
        self.assertEqual(hits, ["QUEEN", "SEC"])

    def test_card_mouse_press_routes_selection(self):
        hits = []
        self.sb.agent_selected.connect(hits.append)
        card = next(c for c in self.sb._cards if c.agent_id == "MTG")
        card.mousePressEvent(None)  # overridden lambda in Sidebar.__init__
        self.assertEqual(hits, ["MTG"])
        self.assertTrue(card._active)

    def test_quick_action_buttons_emit_signals(self):
        hits = []
        for name in (
            "toggle_3d_core", "toggle_dashboard", "toggle_permissions",
            "toggle_settings", "clear_chat",
        ):
            getattr(self.sb, name).connect(lambda n=name: hits.append(n))
        buttons = self.sb.findChildren(QPushButton)
        self.assertEqual(len(buttons), 5)
        for button in buttons:
            button.click()
        self.assertEqual(
            hits,
            ["toggle_3d_core", "toggle_dashboard", "toggle_permissions",
             "toggle_settings", "clear_chat"],
        )
        self.assertIn("3D Hologram", buttons[0].text())
        self.assertIn("Clear Chat", buttons[-1].text())


class TestStatusBar(unittest.TestCase):
    def setUp(self):
        self.sb = ld.StatusBar()
        self.addCleanup(self.sb.deleteLater)

    def test_init(self):
        self.assertEqual(self.sb.height(), 28)
        self.assertEqual(self.sb.sl.text(), "Ready")
        self.assertEqual(self.sb.ml.text(), "model: default")
        self.assertEqual(self.sb.ul.text(), "00:00")
        labels = [l.text() for l in self.sb.findChildren(QLabel)]
        self.assertIn(f"{ld.HOST}:{ld.PORT}", labels)
        self.assertTrue(self.sb._timer.isActive())
        self.assertEqual(self.sb._timer.interval(), 1000)

    def test_set_status_default_color(self):
        self.sb.set_status("Working")
        self.assertEqual(self.sb.sl.text(), "Working")
        self.assertIn(ld.C["text_faint"], self.sb.sl.styleSheet())
        self.assertIn(ld.C["text_faint"], self.sb.dot.styleSheet())

    def test_set_status_custom_color(self):
        self.sb.set_status("Up", ld.C["success"])
        self.assertIn(ld.C["success"], self.sb.sl.styleSheet())
        self.assertIn(ld.C["success"], self.sb.dot.styleSheet())

    def test_tick_formats_uptime(self):
        self.sb._t0 = time.time() - 65
        self.sb._tick()
        self.assertEqual(self.sb.ul.text(), "01:05")
        self.sb._t0 = time.time() - 5
        self.sb._tick()
        self.assertEqual(self.sb.ul.text(), "00:05")


class TestOrbitWindowCore(unittest.TestCase):
    def setUp(self):
        self.win = ld.orbitWindow()
        self.addCleanup(self.win.deleteLater)

    def test_construction(self):
        self.assertTrue(int(self.win.windowFlags()) & int(Qt.FramelessWindowHint))
        self.assertEqual(self.win.minimumSize().width(), 1024)
        self.assertEqual(self.win.minimumSize().height(), 680)
        self.assertIsNotNone(self.win.title_bar)
        self.assertIsNotNone(self.win.sidebar)
        self.assertIsNotNone(self.win.status_bar)
        self.assertIsNone(self.win.web)
        self.assertEqual(self.win._panels, {})
        self.assertFalse(self.win._max)

    def test_set_web_view_inserts_at_index_zero(self):
        web = QLabel()
        self.addCleanup(web.deleteLater)
        self.win.set_web_view(web)
        self.assertIs(self.win.web, web)
        self.assertIs(self.win._stack.widget(0), web)
        self.assertEqual(self.win._stack.currentIndex(), 0)
        self.assertEqual(web.contextMenuPolicy(), Qt.NoContextMenu)

        other = QLabel()
        self.addCleanup(other.deleteLater)
        self.win.set_web_view(other)  # second call must be ignored
        self.assertIs(self.win.web, web)
        self.assertEqual(self.win._stack.count(), 1)

    def test_agent_sel_dispatches_js(self):
        self.win.web = mock.MagicMock()
        self.win._agent_sel("PLN")
        js = self.win.web.page().runJavaScript.call_args[0][0]
        self.assertIn("orbit:agent-select", js)
        self.assertIn("agentId:'PLN'", js)

    def test_agent_sel_without_web_is_noop(self):
        self.win.web = None
        self.win._agent_sel("PLN")  # must not raise

    def test_panel_and_show_web_switch_stack(self):
        web = QLabel()
        self.addCleanup(web.deleteLater)
        self.win.set_web_view(web)
        self.win._active_panel = "dashboard"

        self.win._panel("dashboard")
        self.assertIs(self.win._stack.currentWidget(), web)

        self.win._show_web()
        self.assertIs(self.win._stack.currentWidget(), web)
        self.assertIsNone(self.win._active_panel)

    def test_panel_without_web_is_noop(self):
        self.win.web = None
        self.win._panel("x")
        self.win._show_web()
        self.assertIsNone(self.win._active_panel)

    def test_js_action_mapping(self):
        self.win.web = mock.MagicMock()
        cases = [
            ("toggleDashboard", "dashboard"),
            ("toggleSettings", "settings"),
            ("togglePermissions", "permissions"),
            ("clearChat", "clear"),
            ("unknownAction", "unknownAction"),
        ]
        for action, expected in cases:
            with self.subTest(action=action):
                self.win.web.page().runJavaScript.reset_mock()
                self.win._js(action)
                js = self.win.web.page().runJavaScript.call_args[0][0]
                self.assertIn(f"__orbit_action('{expected}')", js)

    def test_js_without_web_is_noop(self):
        self.win.web = None
        self.win._js("clearChat")

    def test_cmd_dispatches_custom_event(self):
        self.win.web = mock.MagicMock()
        self.win._cmd("3d-hub")
        js = self.win.web.page().runJavaScript.call_args[0][0]
        self.assertIn("orbit-command", js)
        self.assertIn("detail:'3d-hub'", js)

    def test_cmd_without_web_is_noop(self):
        self.win.web = None
        self.win._cmd("3d-hub")

    def test_toggle_max_and_restore(self):
        self.win._toggle_max()
        self.assertTrue(self.win._max)
        self.assertIsNotNone(self.win._geo)
        self.assertEqual(self.win._geo.size().width(), 1400)

        saved = self.win._geo
        self.win._toggle_max()
        self.assertFalse(self.win._max)
        self.assertEqual(self.win.geometry(), saved)

    def test_close_hides_to_tray_when_visible(self):
        self.win.tray = mock.Mock()
        self.win.tray.isVisible.return_value = True
        self.win._close()
        self.win.tray.hide.assert_not_called()  # tray stays alive in background
        args = self.win.tray.showMessage.call_args[0]
        self.assertEqual(args[0], "ORBIT")
        self.assertEqual(args[1], "Running in background.")
        self.assertEqual(args[3], 2000)

    def test_close_quits_without_tray(self):
        with mock.patch.object(ld, "QApplication") as app:
            self.win._close()
        app.quit.assert_called_once()

    def test_close_quits_when_tray_hidden(self):
        self.win.tray = mock.Mock()
        self.win.tray.isVisible.return_value = False
        with mock.patch.object(ld, "QApplication") as app:
            self.win._close()
        app.quit.assert_called_once()
        self.win.tray.hide.assert_called_once()  # _quit hides the tray icon

    def test_quit_stops_web_and_hides_tray(self):
        self.win.web = mock.MagicMock()
        self.win.tray = mock.Mock()
        with mock.patch.object(ld, "QApplication") as app:
            self.win._quit()
        self.win.web.stop.assert_called_once()
        self.win.tray.hide.assert_called_once()
        app.quit.assert_called_once()

    def test_quit_without_web_or_tray(self):
        with mock.patch.object(ld, "QApplication") as app:
            self.win._quit()
        app.quit.assert_called_once()

    def test_close_event_hides_to_tray(self):
        self.win.tray = mock.Mock()
        self.win.tray.isVisible.return_value = True
        event = QCloseEvent()
        self.win.closeEvent(event)
        self.assertFalse(event.isAccepted())  # closeEvent called ignore()
        self.win.tray.hide.assert_not_called()  # tray stays; only window hides
        self.assertEqual(self.win.tray.showMessage.call_args[0][1], "Minimized to tray")

    def test_close_event_quits_without_tray(self):
        event = QCloseEvent()
        with mock.patch.object(ld, "QApplication") as app:
            self.win.closeEvent(event)
        app.quit.assert_called_once()

    def test_paint_event(self):
        pixmap = self.win.grab()
        self.assertFalse(pixmap.isNull())


class TestOrbitWindowTrayShortcuts(unittest.TestCase):
    def setUp(self):
        self.win = ld.orbitWindow()
        self.addCleanup(self.win.deleteLater)

    def test_setup_tray(self):
        self.win._setup_tray()
        self.assertFalse(self.win.windowIcon().isNull())
        if not QSystemTrayAvailable():
            self.assertIsNone(self.win.tray)
            return
        self.assertIsNotNone(self.win.tray)
        self.assertEqual(self.win.tray.toolTip(), "ORBIT AI OS")
        menu = self.win.tray.contextMenu()
        texts = [a.text() for a in menu.actions() if a.text()]
        self.assertEqual(texts, ["Show", "Open in Browser", "Reload (F5)", "Quit"])

        # Show action raises the window
        show_action = next(a for a in menu.actions() if a.text() == "Show")
        show_action.trigger()
        self.assertTrue(self.win.isVisible())
        self.win.hide()

        # Open in Browser delegates to QDesktopServices (patched: never open a real browser)
        with mock.patch.object(ld, "QDesktopServices") as desktop:
            browser_action = next(a for a in menu.actions() if a.text() == "Open in Browser")
            browser_action.trigger()
            desktop.openUrl.assert_called_once()
            self.assertIn(ld.HOST, str(desktop.openUrl.call_args[0][0]))

        # Reload with no web view is a safe no-op
        reload_action = next(a for a in menu.actions() if a.text() == "Reload (F5)")
        reload_action.trigger()

        # Double-click / plain click activation branches.
        # NOTE: PyQt5 ActivationReason is a sip enum that does NOT compare equal
        # to ints (and DoubleClick == 2 here), so emit the enum members directly.
        self.win.tray.activated.emit(QSystemTrayIcon.DoubleClick)
        self.assertTrue(self.win.isVisible())
        self.win.hide()
        self.win.tray.activated.emit(QSystemTrayIcon.Trigger)  # no-op
        self.assertFalse(self.win.isVisible())

        with mock.patch.object(ld, "QApplication") as app:
            quit_action = next(a for a in menu.actions() if a.text() == "Quit")
            quit_action.trigger()
        app.quit.assert_called_once()
        self.assertFalse(self.win.tray.isVisible())  # _quit hid it

    def test_setup_shortcuts(self):
        self.win._setup_shortcuts()
        shortcuts = self.win.findChildren(QShortcut)
        self.assertEqual(len(shortcuts), 4)
        by_key = {s.key().toString(): s for s in shortcuts}
        self.assertEqual(set(by_key), {"F5", "F11", "Esc", "Ctrl+Q"})

        # F5 (no web view) and F11 (maximize) run against the real QApplication
        by_key["F5"].activated.emit()
        by_key["F11"].activated.emit()
        self.assertTrue(self.win._max)

        # Escape and Ctrl+Q reach _quit -> QApplication.quit (mocked)
        with mock.patch.object(ld, "QApplication") as app:
            by_key["Esc"].activated.emit()
            by_key["Ctrl+Q"].activated.emit()
        app.quit.assert_called()


def QSystemTrayAvailable():
    from PyQt5.QtWidgets import QSystemTrayIcon

    return QSystemTrayIcon.isSystemTrayAvailable()


class TestStartupSequence(unittest.TestCase):
    """run_startup_sequence imports `orbit.orbit.core.startup` inside the
    function — inject a fake module to control the import (same technique as
    tests/test_boot_wiring.py)."""

    def _inject(self, module):
        core_pkg = types.ModuleType("orbit.orbit.core")
        core_pkg.__path__ = []
        saved = {}
        for name in ("orbit.orbit.core", "orbit.orbit.core.startup"):
            saved[name] = sys.modules.get(name)
        sys.modules["orbit.orbit.core"] = core_pkg
        sys.modules["orbit.orbit.core.startup"] = module
        return saved

    def _restore(self, saved):
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def test_skip_values(self):
        for value in ("1", "true", "TRUE", "yes", "on", " 1 "):
            with self.subTest(value=value):
                fake = types.ModuleType("orbit.orbit.core.startup")
                fake.get_startup = mock.Mock()
                saved = self._inject(fake)
                try:
                    with mock.patch.dict(os.environ, {"ORBIT_SKIP_STARTUP": value}):
                        ld.run_startup_sequence()
                    fake.get_startup.assert_not_called()
                finally:
                    self._restore(saved)

    def test_import_failure_is_soft(self):
        fake = types.ModuleType("orbit.orbit.core.startup")  # no get_startup attr
        saved = self._inject(fake)
        try:
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ORBIT_SKIP_STARTUP", None)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    ld.run_startup_sequence()
            self.assertIn("Boot sequence unavailable:", buf.getvalue())
        finally:
            self._restore(saved)

    def test_progress_callback_is_forwarded(self):
        captured = {}

        def run_startup(on_progress=None):
            captured["on_progress"] = on_progress
            return {
                "elapsed_ms": 12.5,
                "boot_message": "done",
                "summary": {"total": 18, "passed": 18, "failed": 0},
            }

        seq = mock.Mock()
        seq.run_startup.side_effect = run_startup
        get_startup = mock.Mock(return_value=seq)
        fake = types.ModuleType("orbit.orbit.core.startup")
        fake.get_startup = get_startup
        saved = self._inject(fake)
        try:
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ORBIT_SKIP_STARTUP", None)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    ld.run_startup_sequence()
            self.assertIn("Boot complete in 12.5ms — done", buf.getvalue())
            cb = captured["on_progress"]
            self.assertIsNotNone(cb)
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                cb(3, 18, "warm_cache", "ok")
            self.assertIn("[boot 3/18] warm_cache: ok", buf2.getvalue())
        finally:
            self._restore(saved)


class TestServerHelpers(unittest.TestCase):
    def test_start_server_runs_factory(self):
        with (
            mock.patch.object(ld, "run_startup_sequence") as boot,
            mock.patch("orbit.orbit.server.create_app") as create,
        ):
            ld.start_server()
        boot.assert_called_once()
        create.assert_called_once()
        create.return_value.run.assert_called_once_with(
            host=ld.HOST, port=ld.PORT, debug=False, use_reloader=False, threaded=True
        )

    def test_start_server_swallows_errors(self):
        with (
            mock.patch.object(ld, "run_startup_sequence"),
            mock.patch("orbit.orbit.server.create_app", side_effect=RuntimeError("nope")),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ld.start_server()  # must not raise
        self.assertIn("Server error: nope", buf.getvalue())

    def test_wait_server_success(self):
        with mock.patch("urllib.request.urlopen", return_value=mock.MagicMock()) as urlopen:
            self.assertTrue(ld.wait_server("http://127.0.0.1:5000/", timeout=5))
        urlopen.assert_called_once()

    def test_wait_server_http_error_counts_as_up(self):
        err = urllib.error.HTTPError("http://x", 500, "err", None, None)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertTrue(ld.wait_server("http://127.0.0.1:5000/", timeout=5))

    def test_wait_server_retries_until_ready(self):
        err = urllib.error.URLError("connection refused")
        with (
            mock.patch("urllib.request.urlopen", side_effect=[err, mock.MagicMock()]) as urlopen,
            mock.patch.object(ld.time, "sleep") as sleep,
        ):
            self.assertTrue(ld.wait_server("http://127.0.0.1:5000/", timeout=5))
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.3)

    def test_wait_server_times_out(self):
        err = urllib.error.URLError("down")
        with (
            mock.patch("urllib.request.urlopen", side_effect=err) as urlopen,
            mock.patch.object(ld.time, "sleep"),
        ):
            self.assertFalse(ld.wait_server("http://127.0.0.1:5000/", timeout=0.05))
        self.assertGreater(urlopen.call_count, 0)


class TestMain(unittest.TestCase):
    def test_main_exits_when_server_never_comes_up(self):
        argv = list(sys.argv)
        try:
            with (
                mock.patch.object(ld, "start_server"),
                mock.patch.object(ld, "wait_server", return_value=False),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    with self.assertRaises(SystemExit) as cm:
                        ld.main()
        finally:
            sys.argv[:] = argv
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("ERROR: Server failed to start", buf.getvalue())

    def _run_gui_main(self, urlopen_patch, web_cls=_FakeWeb, webengine=True):
        # NOTE: test_desktop.py / test_widgets.py create a QApplication at
        # module import, so by the time this module is imported QtWebEngine may
        # already be un-importable (ld.WEBENGINE=False, no QWebEngineView
        # attr). Force both deterministically: patch WEBENGINE explicitly and
        # create=True for QWebEngineView.
        argv = list(sys.argv)
        try:
            with (
                mock.patch.object(ld, "start_server"),
                mock.patch.object(ld, "wait_server", return_value=True),
                mock.patch.object(ld, "SplashOverlay", _AutoSplash),
                mock.patch.object(ld, "QWebEngineView", web_cls, create=True),
                mock.patch.object(ld, "QSystemTrayIcon") as tray_cls,
                mock.patch.object(ld, "QApplication") as app_cls,
                mock.patch.object(ld, "WEBENGINE", webengine),
                urlopen_patch,
            ):
                tray_cls.isSystemTrayAvailable.return_value = False
                app_cls.return_value.exec_.side_effect = _drain
                buf = io.StringIO()
                with redirect_stdout(buf):
                    with self.assertRaises(SystemExit) as cm:
                        ld.main()
        finally:
            sys.argv[:] = argv
        return cm.exception.code, buf.getvalue()

    def test_main_full_gui_flow_healthy(self):
        code, out = self._run_gui_main(
            mock.patch("urllib.request.urlopen", return_value=mock.MagicMock())
        )
        self.assertEqual(code, 0)
        self.assertIn("Server ready!", out)
        self.assertIn("Page loaded: True", out)
        self.assertIn("Window ready! F5=Reload F11=Max Ctrl+Q=Quit", out)

    def test_main_full_gui_flow_health_check_fails(self):
        err = urllib.error.URLError("server down")
        code, out = self._run_gui_main(
            mock.patch("urllib.request.urlopen", side_effect=err)
        )
        self.assertEqual(code, 0)
        self.assertIn("Window ready!", out)

    def test_main_without_webengine_falls_back(self):
        # WEBENGINE=False: on_splash_done prints the error and shows the window
        # without ever loading a page.
        code, out = self._run_gui_main(
            mock.patch("urllib.request.urlopen", return_value=mock.MagicMock()),
            webengine=False,
        )
        self.assertEqual(code, 0)
        self.assertIn("Server ready!", out)
        self.assertIn("ERROR: PyQtWebEngine not installed", out)
        self.assertNotIn("Page loaded:", out)

    def test_main_web_settings_failures_are_soft(self):
        # page().settings()/profile() raising must not abort startup.
        code, out = self._run_gui_main(
            mock.patch("urllib.request.urlopen", return_value=mock.MagicMock()),
            web_cls=_BrokenSettingsWeb,
        )
        self.assertEqual(code, 0)
        self.assertIn("Page loaded: True", out)
        self.assertIn("Window ready!", out)


if __name__ == "__main__":
    unittest.main()
