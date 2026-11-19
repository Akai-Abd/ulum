import subprocess
from ulum.adapters.apt import AptAdapter
from ulum.adapters.flatpak import FlatpakAdapter
from ulum.adapters.snap import SnapAdapter
from ulum.core.models import ApplicationRecord, ScopeType, SourceType

def test_apt_adapter_list_installed(monkeypatch):
    adapter = AptAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)

    def mock_run_cmd(cmd, **kwargs):
        stdout = "curl\t7.88.1-10+deb12u5\tinstall ok installed\nvim\t2:9.0.1378-2\tinstall ok installed\n"
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

    import ulum.adapters.apt as apt_module
    monkeypatch.setattr(apt_module, "run_cmd", mock_run_cmd)

    apps = adapter.list_installed()
    assert len(apps) == 2
    assert apps[0].package_id == "curl"
    assert apps[0].installed_version == "7.88.1-10+deb12u5"
    assert apps[1].package_id == "vim"

def test_apt_adapter_check_updates(monkeypatch):
    adapter = AptAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)

    installed_app = ApplicationRecord(
        source=SourceType.APT,
        source_scope=ScopeType.SYSTEM,
        package_id="curl",
        display_name="curl",
        installed_version="7.88.1",
    )
    monkeypatch.setattr(adapter, "list_installed", lambda: [installed_app])

    def mock_run_cmd(cmd, **kwargs):
        stdout = "Inst curl [7.88.1] (7.88.2 amd64)\nConf curl (7.88.2 amd64)\n"
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

    import ulum.adapters.apt as apt_module
    monkeypatch.setattr(apt_module, "run_cmd", mock_run_cmd)

    updates = adapter.check_updates(refresh=False)
    assert len(updates) == 1
    assert updates[0].application.package_id == "curl"
    assert updates[0].available_version == "7.88.2"

def test_flatpak_adapter_list_installed(monkeypatch):
    adapter = FlatpakAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)

    def mock_run_cmd(cmd, **kwargs):
        stdout = "org.mozilla.firefox\tFirefox\t125.0.3\tsystem\norg.signal.Signal\tSignal\t7.1.0\tuser\n"
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

    import ulum.adapters.flatpak as flatpak_module
    monkeypatch.setattr(flatpak_module, "run_cmd", mock_run_cmd)

    apps = adapter.list_installed()
    assert len(apps) == 2
    assert apps[0].package_id == "org.mozilla.firefox"
    assert apps[0].source_scope == ScopeType.SYSTEM
    assert apps[1].package_id == "org.signal.Signal"
    assert apps[1].source_scope == ScopeType.USER

def test_snap_adapter_list_installed(monkeypatch):
    adapter = SnapAdapter()
    monkeypatch.setattr(adapter, "is_available", lambda: True)

    def mock_run_cmd(cmd, **kwargs):
        stdout = "Name  Version  Rev  Tracking  Publisher  Notes\ncore22  20240111  1122  latest/stable  canonical✓  base\nvlc  3.0.20  3721  latest/stable  videolan✓  -\n"
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

    import ulum.adapters.snap as snap_module
    monkeypatch.setattr(snap_module, "run_cmd", mock_run_cmd)

    apps = adapter.list_installed()
    assert len(apps) == 2
    assert apps[0].package_id == "core22"
    assert apps[1].package_id == "vlc"
