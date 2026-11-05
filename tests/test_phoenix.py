import json
import tempfile
from pathlib import Path

import pytest


class TestCheckpoint:
    def test_import(self):
        from orbit.orbit.core.phoenix import Checkpoint

        assert Checkpoint is not None

    def test_create_and_save(self):
        from orbit.orbit.core.phoenix import Checkpoint

        cp = Checkpoint("test_label", {"key": "value"})
        assert cp.label == "test_label"
        assert cp.data == {"key": "value"}
        assert cp.id.startswith("cp_")
        path = cp.save()
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["label"] == "test_label"

    def test_latest_without_label(self):
        from orbit.orbit.core.phoenix import Checkpoint

        cp = Checkpoint("latest_test", {"x": 1})
        cp.save()
        found = Checkpoint.latest()
        assert found is not None
        assert "label" in found


class TestPhoenixEngine:
    def test_import(self):
        from orbit.orbit.core.phoenix import PhoenixEngine

        assert PhoenixEngine is not None

    def test_singleton(self):
        from orbit.orbit.core.phoenix import get_phoenix

        p1 = get_phoenix()
        p2 = get_phoenix()
        assert p1 is p2

    def test_take_checkpoint(self):
        from orbit.orbit.core.phoenix import take_checkpoint

        result = take_checkpoint("test_checkpoint")
        assert "event" in result
        assert result["label"] == "test_checkpoint"

    def test_check_health(self):
        from orbit.orbit.core.phoenix import check_health

        health = check_health()
        assert "overall" in health
        assert "time" in health
        assert "checks" in health

    def test_create_backup_archive(self):
        from unittest.mock import patch

        from orbit.orbit.core.phoenix import get_phoenix

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            data_dir = tmp / "data"
            data_dir.mkdir()
            checkpoint_dir = tmp / "checkpoints"
            checkpoint_dir.mkdir()
            backup_dir = tmp / "backups"
            backup_dir.mkdir()
            # Write a small test file
            (data_dir / "test.txt").write_text("hello")
            with (
                patch("orbit.orbit.core.phoenix.DATA_DIR", data_dir),
                patch("orbit.orbit.core.phoenix.CHECKPOINT_DIR", checkpoint_dir),
                patch("orbit.orbit.core.phoenix.BACKUP_DIR", backup_dir),
            ):
                p = get_phoenix()
                result = p.create_backup_archive("test_archive")
                assert "event" in result
                assert result["event"] == "backup"
                assert "id" in result

    def test_list_backups_returns_list(self):
        from orbit.orbit.core.phoenix import get_phoenix

        p = get_phoenix()
        backups = p.list_backups()
        assert isinstance(backups, list)

    def test_get_history_returns_list(self):
        from orbit.orbit.core.phoenix import get_phoenix

        p = get_phoenix()
        hist = p.get_history()
        assert isinstance(hist, list)

    def test_get_stats(self):
        from orbit.orbit.core.phoenix import get_phoenix

        p = get_phoenix()
        stats = p.get_stats()
        assert "total_events" in stats
        assert "today_events" in stats

    def test_health_check_register_and_run(self):
        from orbit.orbit.core.phoenix import check_health, register_health_check

        register_health_check("test_check", lambda: {"status": "ok"})
        health = check_health()
        assert "test_check" in health["checks"]
        assert health["checks"]["test_check"]["status"] == "ok"

    def test_health_check_failure_isolated(self):
        from orbit.orbit.core.phoenix import check_health, register_health_check

        register_health_check(
            "failing_check", lambda: {"status": "error", "error": "test"}
        )
        health = check_health()
        assert health["checks"]["failing_check"]["status"] == "error"
        assert health["overall"] == "degraded"


class TestModuleFunctions:
    def test_take_checkpoint_module(self):
        from orbit.orbit.core.phoenix import take_checkpoint

        result = take_checkpoint("module_test")
        assert result["event"] == "checkpoint"

    def test_check_health_module(self):
        from orbit.orbit.core.phoenix import check_health

        h = check_health()
        assert isinstance(h, dict)

    def test_get_phoenix_stats_module(self):
        from orbit.orbit.core.phoenix import get_phoenix_stats

        s = get_phoenix_stats()
        assert isinstance(s, dict)

    def test_get_phoenix_history_module(self):
        from orbit.orbit.core.phoenix import get_phoenix_history

        h = get_phoenix_history()
        assert isinstance(h, list)


class TestPhoenixBlueprint:
    def test_blueprint_import(self):
        from orbit.orbit.core.phoenix_bp import phoenix_bp

        assert phoenix_bp is not None
        assert phoenix_bp.name == "phoenix"

    def test_blueprint_registration(self):
        from flask import Flask

        from orbit.orbit.core.phoenix_bp import phoenix_bp

        app = Flask(__name__)
        app.register_blueprint(phoenix_bp)
        rules = [r.rule for r in app.url_map.iter_rules()]
        phoenix_rules = [r for r in rules if "/api/phoenix/" in r]
        assert len(phoenix_rules) > 0


class TestEmergencyRecovery:
    def _has_script(self):
        return (Path(__file__).parent.parent / "emergency_recovery.py").exists()

    @pytest.mark.skipif(
        not Path(__file__).parent.parent.joinpath("emergency_recovery.py").exists(),
        reason="emergency_recovery.py not present",
    )
    def test_import(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "emergency_recovery",
            str(Path(__file__).parent.parent / "emergency_recovery.py"),
        )
        assert spec is not None
        assert spec.loader is not None

    @pytest.mark.skipif(
        not Path(__file__).parent.parent.joinpath("emergency_recovery.py").exists(),
        reason="emergency_recovery.py not present",
    )
    def test_cli_help(self):
        import subprocess
        import sys

        r = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent / "emergency_recovery.py"),
                "--help",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert r.returncode == 0

    @pytest.mark.skipif(
        not Path(__file__).parent.parent.joinpath("emergency_recovery.py").exists(),
        reason="emergency_recovery.py not present",
    )
    def test_cli_check(self):
        import subprocess
        import sys

        r = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent / "emergency_recovery.py"),
                "--check",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert r.returncode in (0, 1)

    @pytest.mark.skipif(
        not Path(__file__).parent.parent.joinpath("emergency_recovery.py").exists(),
        reason="emergency_recovery.py not present",
    )
    def test_cli_snapshot(self):
        import subprocess
        import sys

        r = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent / "emergency_recovery.py"),
                "--snapshot",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert r.returncode == 0
