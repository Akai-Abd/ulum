from pathlib import Path
from ulum.core.models import ApplicationRecord, ScopeType, SourceType
from ulum.removal.leftovers import LeftoverScanner

def test_leftover_scanner_detects_uninstalled_flatpak(temp_db, tmp_path, monkeypatch):
    repo, _ = temp_db
    fake_home = tmp_path / "home"
    var_app = fake_home / ".var" / "app"
    var_app.mkdir(parents=True)
    
    # One installed flatpak app, one leftover dir
    app = ApplicationRecord(
        source=SourceType.FLATPAK,
        source_scope=ScopeType.USER,
        package_id="org.mozilla.firefox",
        display_name="Firefox",
        installed_version="125.0",
    )
    repo.save_applications([app])

    # Leftover directory: org.videolan.vlc
    leftover_dir = var_app / "org.videolan.vlc"
    leftover_dir.mkdir()
    (leftover_dir / "cache.bin").write_text("data", encoding="utf-8")

    # Valid directory for installed app
    (var_app / "org.mozilla.firefox").mkdir()

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    scanner = LeftoverScanner(repo)
    candidates = scanner.scan_leftovers()

    assert len(candidates) == 1
    assert candidates[0].path == leftover_dir
    assert candidates[0].candidate_type == "flatpak_data"
    assert candidates[0].confidence.value == "verified"

def test_leftover_scanner_aborts_on_empty_inventory(temp_db, tmp_path, monkeypatch):
    repo, _ = temp_db
    fake_home = tmp_path / "home"
    var_app = fake_home / ".var" / "app"
    var_app.mkdir(parents=True)
    (var_app / "org.mozilla.firefox").mkdir()

    monkeypatch.setattr(Path, "home", lambda: fake_home)
    scanner = LeftoverScanner(repo)
    # Empty inventory in DB must return 0 candidates to prevent accidental wipe
    assert scanner.scan_leftovers() == []

def test_leftover_scanner_protects_desktop_and_substring_apps(temp_db, tmp_path, monkeypatch):
    repo, _ = temp_db
    fake_home = tmp_path / "home"
    config_dir = fake_home / ".config"
    config_dir.mkdir(parents=True)

    # Installed: google-chrome-stable
    app = ApplicationRecord(
        source=SourceType.APT,
        source_scope=ScopeType.SYSTEM,
        package_id="google-chrome-stable",
        display_name="Google Chrome",
        installed_version="125.0",
    )
    repo.save_applications([app])

    # 1. Config dir named "google-chrome" (substring of package)
    (config_dir / "google-chrome").mkdir()
    # 2. Config dir named "dconf" or "cinnamon" (desktop environment generic dirs)
    (config_dir / "cinnamon").mkdir()
    (config_dir / "dconf").mkdir()
    # 3. Real leftover
    (config_dir / "uninstalled-old-app").mkdir()

    monkeypatch.setattr(Path, "home", lambda: fake_home)
    scanner = LeftoverScanner(repo)
    candidates = scanner.scan_leftovers()

    assert len(candidates) == 1
    assert candidates[0].path == config_dir / "uninstalled-old-app"
