from pathlib import Path
from ulum.core.config import UlumConfig, load_config
from ulum.core.system import get_system_info, parse_os_release

def test_parse_os_release(tmp_path):
    os_rel = tmp_path / "os-release"
    os_rel.write_text(
        'NAME="Linux Mint"\nVERSION="22.1 (Xia)"\nID=linuxmint\nVERSION_ID="22.1"\n',
        encoding="utf-8",
    )
    data = parse_os_release(os_rel)
    assert data["ID"] == "linuxmint"
    assert data["VERSION_ID"] == "22.1"

    info = get_system_info(os_release_path=os_rel)
    assert info.distro_id == "linuxmint"
    assert info.distro_version == "22.1"
    assert info.is_supported is True

def test_config_loader(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        'enabled_adapters = ["apt", "flatpak"]\nexcluded_packages = ["apt:held-pkg"]\nrequire_confirmation = false\n',
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.enabled_adapters == ["apt", "flatpak"]
    assert cfg.excluded_packages == ["apt:held-pkg"]
    assert cfg.require_confirmation is False


def test_run_cmd_elevation_pkexec(monkeypatch):
    import subprocess
    import sys
    from ulum.utils.process import run_cmd

    captured_cmds = []

    monkeypatch.setattr("ulum.utils.process.is_root", lambda: False)
    monkeypatch.setattr("ulum.utils.process.command_exists", lambda b: True)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    def mock_subprocess_run(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        if cmd == ["sudo", "-n", "true"]:
            return subprocess.CompletedProcess(cmd, 1, "", "password required")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    res = run_cmd(["apt-get", "install", "-y", "pkg"], require_root=True)
    assert res.returncode == 0
    # Must use pkexec in GUI / non-tty when sudo is not passwordless
    assert any("pkexec" in c[0] for c in captured_cmds)

