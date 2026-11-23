from typer.testing import CliRunner
from ulum.cli.app import app

runner = CliRunner()

def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "ULUM version" in result.stdout

def test_cli_sources():
    result = runner.invoke(app, ["sources"])
    assert result.exit_code == 0
    assert "System Status" in result.stdout
    assert "Package Managers" in result.stdout

def test_cli_doctor():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "diagnostic check" in result.stdout.lower()

def test_cli_remove_dry_run(monkeypatch):
    import ulum.cli.app as app_module
    import subprocess
    
    # Mock apt commands to avoid touching system
    def mock_run_cmd(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    import ulum.adapters.apt as apt_module
    monkeypatch.setattr(apt_module, "run_cmd", mock_run_cmd)

    result = runner.invoke(app, ["remove", "apt:nano", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry-run complete" in result.stdout
    assert "Proposed Removal Plan" in result.stdout

def test_cli_update_dry_run(monkeypatch):
    result = runner.invoke(app, ["update", "apt:curl", "--dry-run", "--yes"])
    assert result.exit_code == 0
    assert "DRY-RUN mode" in result.stdout

def test_cli_update_security_only(monkeypatch):
    result = runner.invoke(app, ["update", "--security-only", "--dry-run", "--yes"])
    assert result.exit_code == 0
    assert "Security" in result.stdout
