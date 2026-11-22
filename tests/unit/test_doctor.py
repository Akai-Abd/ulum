"""Tests for SystemDoctor and the 8-point diagnostic checklist."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ulum.cli.app import app
from ulum.doctor.health import DoctorReport, HealthCheckResult, SystemDoctor


def test_doctor_check_distribution():
    res = SystemDoctor.check_distribution()
    assert isinstance(res, HealthCheckResult)
    assert res.name == "distribution"
    assert res.status in ["ok", "warn"]
    assert "Linux" in res.message or "Ubuntu" in res.message or "Mint" in res.message
    assert "arch" in res.details
    assert "kernel" in res.details


def test_doctor_check_package_managers():
    res = SystemDoctor.check_package_managers()
    assert isinstance(res, HealthCheckResult)
    assert res.name == "package_managers"
    assert "apt" in res.details
    assert res.status in ["ok", "warn"]


def test_doctor_check_boot_health():
    res = SystemDoctor.check_boot_health()
    assert isinstance(res, HealthCheckResult)
    assert res.name == "boot_health"
    assert "free_mb" in res.details
    assert "installed_kernels_count" in res.details
    assert "booted_kernel" in res.details


def test_doctor_check_database(tmp_path: Path):
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA user_version = 2")
    conn.close()

    res = SystemDoctor.check_database(db_path=db_file)
    assert res.status == "ok"
    assert res.details["schema_version"] == 2
    assert res.details["exists"] is True


def test_doctor_check_locks_free():
    with patch.object(SystemDoctor, "get_holding_pids", return_value=[]):
        res = SystemDoctor.check_locks()
        assert res.status == "ok"
        assert res.details["is_locked"] is False


def test_doctor_check_locks_stale():
    # Simulate a lock file held by defunct PID 999999
    with patch("pathlib.Path.exists", return_value=True), \
         patch.object(SystemDoctor, "get_holding_pids", return_value=[999999]), \
         patch("os.kill", side_effect=OSError("No such process")):
        res = SystemDoctor.check_locks()
        assert res.status == "fail"
        assert "Stale lock" in res.message


def test_doctor_check_scan_freshness_none(tmp_path: Path):
    db_file = tmp_path / "empty.db"
    res = SystemDoctor.check_scan_freshness(db_path=db_file)
    assert res.status == "warn"
    assert "No inventory scan" in res.message


def test_doctor_run_all_checks():
    report = SystemDoctor.run_all_checks(check_online=False)
    assert isinstance(report, DoctorReport)
    assert len(report.checks) == 8
    assert report.exit_code in [0, 1]
    assert report.overall_status in ["healthy", "degraded", "failed"]

    names = [c.name for c in report.checks]
    expected_order = [
        "distribution",
        "package_managers",
        "repositories",
        "boot_health",
        "database",
        "locks",
        "scan_freshness",
        "version",
    ]
    assert names == expected_order


def test_cli_doctor_json():
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "--json"])
    # Should output valid JSON
    assert result.exit_code in [0, 1]
    data = json.loads(result.stdout)
    assert "overall_status" in data
    assert "checks" in data
    assert len(data["checks"]) == 8
    assert "timestamp" in data


def test_cli_doctor_human():
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code in [0, 1]
    assert "ULUM Health Diagnostics (8-Point Checklist)" in result.stdout
    assert "1. Distribution & Kernel:" in result.stdout
    assert "2. Package Managers:" in result.stdout
    assert "4. /boot Partition & Kernel Health:" in result.stdout
