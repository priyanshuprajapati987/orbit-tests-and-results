"""Unit tests for orbit/orbit/core/websocket_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.websocket_bp as wsbp
from orbit.core.websocket_bp import create_socketio, get_socketio


class TestWebsocketBp(unittest.TestCase):
    def setUp(self):
        wsbp._sio = None

    def tearDown(self):
        wsbp._sio = None

    def test_no_flask_socketio(self):
        with patch.dict(sys.modules, {"flask_socketio": None}):
            r = create_socketio(MagicMock())
        self.assertIsNone(r)

    def test_create_socketio_success(self):
        sio_instance = MagicMock()
        socketio_cls = MagicMock(return_value=sio_instance)
        flask_socketio_mod = MagicMock()
        flask_socketio_mod.SocketIO = socketio_cls
        with patch.dict(sys.modules, {"flask_socketio": flask_socketio_mod}):
            app = MagicMock()
            r = create_socketio(app)
        self.assertIs(r, sio_instance)
        socketio_cls.assert_called_once_with(app, cors_allowed_origins="*")

    def test_get_socketio_none_without_app(self):
        self.assertIsNone(get_socketio())

    def test_get_socketio_creates_with_app(self):
        sio_instance = MagicMock()
        socketio_cls = MagicMock(return_value=sio_instance)
        flask_socketio_mod = MagicMock()
        flask_socketio_mod.SocketIO = socketio_cls
        with patch.dict(sys.modules, {"flask_socketio": flask_socketio_mod}):
            r = get_socketio(MagicMock())
        self.assertIs(r, sio_instance)

    def test_get_socketio_cached(self):
        sio_instance = MagicMock()
        wsbp._sio = sio_instance
        self.assertIs(get_socketio(MagicMock()), sio_instance)


if __name__ == "__main__":
    unittest.main()
