import subprocess
from ulum.adapters.apt import AptAdapter, parse_apt_upgradable_line
from ulum.adapters.flatpak import FlatpakAdapter
from ulum.adapters.snap import SnapAdapter
from ulum.core.models import ApplicationRecord, ScopeType, SourceType

def test_parse_apt_upgradable_line():
    sec_line = "curl/noble-security 7.88.1-10ubuntu2.4 amd64 [upgradable from: 7.88.1-10ubuntu2.3]"
    parsed_sec = parse_apt_upgradable_line(sec_line)
    assert parsed_sec is not None
    assert parsed_sec["package_id"] == "curl"
    assert parsed_sec["available_version"] == "7.88.1-10ubuntu2.4"
    assert parsed_sec["current_version"] == "7.88.1-10ubuntu2.3"
    assert parsed_sec["urgency"] == "Security"

    multi_origin_sec = "libssl3/noble-updates,noble-security 3.0.13-0ubuntu3.4 amd64 [upgradable from: 3.0.13-0ubuntu3.3]"
    parsed_multi = parse_apt_upgradable_line(multi_origin_sec)
    assert parsed_multi is not None
    assert parsed_multi["urgency"] == "Security"

    non_sec_line = "vim/noble-updates 2:9.1.0016-1ubuntu7.3 amd64 [upgradable from: 2:9.1.0016-1ubuntu7.1]"
    parsed_non_sec = parse_apt_upgradable_line(non_sec_line)
    assert parsed_non_sec is not None
    assert parsed_non_sec["urgency"] == "Unknown"

    header_line = "Listing... Done"
    assert parse_apt_upgradable_line(header_line) is None

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

def test_appimage_adapter(tmp_path, monkeypatch):
    from ulum.adapters.appimage import AppImageAdapter
    adapter = AppImageAdapter()
    app_dir = tmp_path / "Applications"
    app_dir.mkdir()
    fake_app = app_dir / "Cursor-0.45.1.AppImage"
    fake_app.write_text("binary", encoding="utf-8")

    monkeypatch.setattr(adapter, "_get_search_dirs", lambda: [app_dir])
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    apps = adapter.list_installed()
    assert len(apps) == 1
    assert apps[0].package_id == "cursor-0.45.1"
    assert apps[0].installed_version == "0.45.1"

    # Plan removal
    plan = adapter.build_removal_plan(apps[0], complete=True)
    assert plan.is_safe is True
    res = adapter.execute_native_removal(plan)
    assert res.success is True
    assert not fake_app.exists()

def test_appimage_removal_without_cached_location(tmp_path, monkeypatch):
    from ulum.adapters.appimage import AppImageAdapter
    from ulum.core.models import ApplicationRecord, ScopeType, SourceType
    adapter = AppImageAdapter()
    app_dir = tmp_path / "Applications"
    app_dir.mkdir()
    fake_app = app_dir / "Obsidian-1.5.AppImage"
    fake_app.write_text("binary", encoding="utf-8")

    monkeypatch.setattr(adapter, "_get_search_dirs", lambda: [app_dir])
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    app = ApplicationRecord(
        source=SourceType.APPIMAGE,
        source_scope=ScopeType.USER,
        package_id="obsidian-1.5",
        display_name="Obsidian",
        installed_version="1.5",
        install_location=None,
    )
    plan = adapter.build_removal_plan(app, complete=False)
    assert plan.application.install_location == str(fake_app.resolve())
    res = adapter.execute_native_removal(plan)
    assert res.success is True
    assert not fake_app.exists()
