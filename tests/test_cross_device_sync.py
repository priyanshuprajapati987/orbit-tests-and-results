"""Regression tests: CrossDeviceSync is genuinely cross-device (not just local files).

Covers:
- Local backend still propagates between two device ids (data flow).
- Network backend hub endpoints (/api/sync/push|pull|peers) actually store + serve.
- NetworkTransport client serializes to the right URLs and parses responses.
- Network backend gracefully falls back to local when SYNC_HUB_URL is unset.
"""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


from orbit.orbit.core import cross_device_sync as cds
from orbit.orbit.core import safe_http as safe_http_mod
from orbit.orbit.core.cross_device_sync import (
    CrossDeviceSync,
    NetworkTransport,
    _make_transport,
)
from orbit.orbit.server import create_app


def _instance(device_id):
    return CrossDeviceSync.__new__(CrossDeviceSync)


def test_local_backend_two_devices(monkeypatch, tmp_path):
    monkeypatch.setattr(cds, "SYNC_DIR", tmp_path)
    monkeypatch.setattr(cds, "HUB_DIR", tmp_path / "hub")
    (tmp_path / "hub").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cds, "SYNC_BACKEND", "local")

    a = CrossDeviceSync()
    a._device_id = "deviceA"
    b = CrossDeviceSync()
    b._device_id = "deviceB"

    applied = []
    b._apply_remote_change = lambda data: applied.append(data)

    a.queue_change("task_output", {"task_id": "t1", "output": "hello-from-A"})
    a.sync()  # A writes its change to the shared SYNC_DIR
    b.sync()  # B pulls A's change and applies it

    assert any(c.get("data", {}).get("output") == "hello-from-A" for c in applied)


def test_hub_endpoints_store_and_serve(monkeypatch, tmp_path):
    monkeypatch.setattr(cds, "HUB_DIR", tmp_path)
    import orbit.orbit.core.cross_device_sync_bp as sync_bp_mod

    monkeypatch.setattr(sync_bp_mod, "HUB_DIR", tmp_path)
    app = create_app()
    with app.test_client() as c:
        r = c.post(
            "/api/sync/push",
            json={
                "device_id": "devA",
                "kind": "state",
                "payload": {
                    "device_id": "devA",
                    "state": {"preferences": {"theme": "dark"}},
                },
            },
        )
        assert r.status_code == 200
        r = c.post(
            "/api/sync/push",
            json={
                "device_id": "devA",
                "kind": "change",
                "payload": {"type": "task_output", "data": {"x": 1}},
            },
        )
        assert r.status_code == 200

        # devB pulls -> should see devA's data, not its own
        r = c.get("/api/sync/pull/devB")
        assert r.status_code == 200
        body = r.get_json()
        assert any(ch.get("data", {}).get("x") == 1 for ch in body["changes"])
        assert any("preferences" in st.get("state", {}) for st in body["states"])

        r = c.get("/api/sync/peers")
        assert "devA" in r.get_json()["peers"]


def test_hub_rejects_bad_device_id():
    app = create_app()
    with app.test_client() as c:
        r = c.post(
            "/api/sync/push",
            json={"device_id": "../../etc", "kind": "state", "payload": {}},
        )
        assert r.status_code == 400


def test_network_transport_serializes(monkeypatch):
    # Validate the client side without a live server by stubbing safe_http.
    posted, gotten = [], []

    def fake_post(url, json=None, timeout=15):
        posted.append((url, json))

        class R:
            status_code = 200

        return R()

    def fake_get(url, timeout=15):
        gotten.append(url)

        class R:
            status_code = 200

            def json(self):
                return {
                    "changes": [{"type": "task_output", "data": {"x": 1}}],
                    "states": [],
                }

        return R()

    monkeypatch.setattr(safe_http_mod, "safe_requests_post", fake_post)
    monkeypatch.setattr(safe_http_mod, "safe_requests_get", fake_get)

    t = NetworkTransport("http://hub:5000")
    t.push_changes("devB", [{"type": "task_output", "data": {"x": 1}}])
    changes, _states = t.pull("devB")
    assert posted and posted[0][0] == "http://hub:5000/api/sync/push"
    assert gotten and gotten[0] == "http://hub:5000/api/sync/pull/devB"
    assert changes[0]["data"]["x"] == 1


def test_network_falls_back_to_local_when_no_hub(monkeypatch, tmp_path):
    monkeypatch.setattr(cds, "SYNC_BACKEND", "network")
    monkeypatch.setattr(cds, "SYNC_HUB_URL", "")
    monkeypatch.setattr(cds, "SYNC_DIR", tmp_path)
    monkeypatch.setattr(cds, "HUB_DIR", tmp_path / "hub")
    (tmp_path / "hub").mkdir(parents=True, exist_ok=True)
    transport = _make_transport()
    # Should not raise; falls back to LocalTransport
    assert type(transport).__name__ == "LocalTransport"
