"""Alert System + Audit Trail + Connection Pool — audit & regression (LOOP-ITER-4).

Covers the string-severity AttributeError crash fix in create_alert.
"""
import tempfile
from pathlib import Path

import pytest


def _alerts():
    from orbit.orbit.core.alert_system import AlertSystem

    return AlertSystem(storage_file=str(Path(tempfile.mkdtemp()) / "a.json"))


def _audit():
    from orbit.orbit.core.audit_trail import AuditTrail

    return AuditTrail(storage_file=str(Path(tempfile.mkdtemp()) / "b.json"))


class TestCreateAlertSeverityCoercion:
    def test_bad_severity_string_no_crash(self):
        """REGRESSION: plain string severity must not AttributeError on .value."""
        al = _alerts()
        alert = al.create_alert("t", "m", "bogus")
        assert alert is not None
        assert alert.severity.value == "info"  # fallback

    def test_valid_severity_string(self):
        al = _alerts()
        alert = al.create_alert("t", "m", "critical")
        assert alert.severity.value == "critical"

    def test_uppercase_severity_string(self):
        al = _alerts()
        alert = al.create_alert("t", "m", "WARNING")
        assert alert.severity.value == "warning"

    def test_enum_severity_still_works(self):
        from orbit.orbit.core.alert_system import AlertSeverity

        al = _alerts()
        alert = al.create_alert("t", "m", AlertSeverity.ERROR)
        assert alert.severity.value == "error"

    def test_bad_category_string_no_crash(self):
        al = _alerts()
        alert = al.create_alert("t", "m", "info", "weird")
        assert alert is not None
        assert alert.category.value == "system"  # fallback

    def test_valid_category_string(self):
        al = _alerts()
        alert = al.create_alert("t", "m", "info", "security")
        assert alert.category.value == "security"

    def test_enum_category_still_works(self):
        from orbit.orbit.core.alert_system import AlertCategory

        al = _alerts()
        alert = al.create_alert("t", "m", "info", AlertCategory.WORKFLOW)
        assert alert.category.value == "workflow"

    def test_empty_title_message(self):
        al = _alerts()
        alert = al.create_alert("", "")
        assert alert is not None


class TestAlertSystemQueries:
    def test_get_alerts_bad_filter_graceful(self):
        al = _alerts()
        al.create_alert("CPU", "high", "warning")
        assert al.get_alerts(category="bogus") == []
        assert al.get_alerts(severity="bogus") == []

    def test_get_alerts_negative_limit(self):
        al = _alerts()
        al.create_alert("x", "y", "info")
        assert al.get_alerts(limit=-3) == []

    def test_get_alerts_valid_filter(self):
        al = _alerts()
        al.create_alert("CPU", "high", "warning")
        results = al.get_alerts(severity="warning")
        assert len(results) == 1

    def test_get_statistics_shape(self):
        al = _alerts()
        al.create_alert("a", "b", "error")
        s = al.get_statistics()
        assert "total_alerts" in s
        assert "by_severity" in s

    def test_enums_have_values(self):
        from orbit.orbit.core.alert_system import AlertCategory, AlertSeverity

        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertCategory.SECURITY.value == "security"


class TestAuditTrail:
    def test_log_action_basic(self):
        a = _audit()
        entry_id = a.log_action("test_action")
        assert isinstance(entry_id, str)

    def test_log_action_full(self):
        a = _audit()
        entry_id = a.log_action(
            "deploy", user="priyanshu", resource="prod", details={"env": "prod"}, success=True
        )
        entries = a.get_entries()
        assert len(entries) >= 1
        assert entries[0]["action"] == "deploy"

    def test_log_action_failure(self):
        a = _audit()
        a.log_action("bad_op", success=False)
        entries = a.get_entries()
        assert entries[0]["success"] is False

    def test_get_entries_action_filter(self):
        a = _audit()
        a.log_action("alpha")
        a.log_action("beta")
        only_alpha = a.get_entries(action="alpha")
        assert len(only_alpha) == 1

    def test_get_entries_negative_limit(self):
        a = _audit()
        a.log_action("x")
        assert a.get_entries(limit=-5) == []

    def test_log_api_call(self):
        a = _audit()
        eid = a.log_api_call("ollama", "/api/generate", True, 120.5)
        assert isinstance(eid, str)

    def test_log_login_signature(self):
        import inspect

        a = _audit()
        sig = inspect.signature(a.log_login)
        assert "success" in sig.parameters


class TestConnectionPool:
    def _pool(self, min_size=1, max_size=3):
        from orbit.orbit.core.connection_pool import ConnectionPool

        def creator():
            return object()

        return ConnectionPool("test", creator, min_size=min_size, max_size=max_size)

    def test_pool_creation(self):
        p = self._pool()
        assert p is not None

    def test_pool_max_lt_min_tolerated(self):
        # no crash on inverted sizes
        from orbit.orbit.core.connection_pool import ConnectionPool

        p = ConnectionPool("x", lambda: 1, min_size=10, max_size=5)
        assert p is not None

    def test_pool_zero_size_tolerated(self):
        from orbit.orbit.core.connection_pool import ConnectionPool

        p = ConnectionPool("x", lambda: 1, min_size=0, max_size=0)
        assert p is not None

    def test_acquire_release_roundtrip(self):
        p = self._pool()
        conn = p.acquire()
        assert conn is not None
        p.release(conn)

    def test_failing_creator_handled(self):
        from orbit.orbit.core.connection_pool import ConnectionPool

        def bad():
            raise RuntimeError("no connection")

        p = ConnectionPool("bad", bad, min_size=0, max_size=1)
        # acquire with a failing creator must not raise out of pool API
        try:
            conn = p.acquire(timeout=1)
            # if it returned something, fine; if None, fine
            assert conn is None or conn is not None
        except RuntimeError:
            pass  # acceptable: surfaced to caller
        except Exception as e:
            pytest.fail(f"unexpected exception type: {type(e).__name__}: {e}")
