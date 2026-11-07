"""Unit tests for orbit/orbit/core/weather_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.weather_bp import weather_bp


class TestWeatherBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(weather_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(weather_bp.name, "weather_bp")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/weather", rules)

    def test_weather_default_city(self):
        svc = MagicMock()
        svc.get_weather.return_value = {"temp": 30, "city": "Delhi"}
        with patch("orbit.core.weather_bp.get_weather_service", return_value=svc):
            r = self.client.get("/api/weather")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["city"], "Delhi")
        svc.get_weather.assert_called_once_with("Delhi", None, None)

    def test_weather_with_params(self):
        svc = MagicMock()
        svc.get_weather.return_value = {"temp": 25}
        with patch("orbit.core.weather_bp.get_weather_service", return_value=svc):
            r = self.client.get("/api/weather?city=Mumbai&lat=19.0&lon=72.8")
        self.assertEqual(r.status_code, 200)
        svc.get_weather.assert_called_once_with("Mumbai", 19.0, 72.8)


if __name__ == "__main__":
    unittest.main()
