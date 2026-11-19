import os
from pathlib import Path
from ulum.removal.safety import SafetyValidator

def test_system_directories_rejected():
    for sys_dir in ["/", "/usr", "/bin", "/etc", "/lib", "/var"]:
        valid, msg = SafetyValidator.validate_cleanup_path(sys_dir)
        assert not valid
        assert "critical system directory" in msg

def test_user_home_and_personal_dirs_rejected():
    home = Path.home()
    for user_dir in [home, home / "Desktop", home / "Documents", home / "Downloads"]:
        valid, msg = SafetyValidator.validate_cleanup_path(user_dir)
        assert not valid
        assert "protected user directory" in msg

def test_base_cleanup_dirs_cannot_be_deleted_themselves():
    home = Path.home()
    for base in [home / ".config", home / ".cache", home / ".local" / "share", home / "snap"]:
        valid, msg = SafetyValidator.validate_cleanup_path(base)
        assert not valid
        assert "Cannot delete base directory" in msg

def test_allowed_app_directory_accepted(tmp_path, monkeypatch):
    home = tmp_path / "fakehome"
    config_dir = home / ".config" / "testapp"
    config_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    valid, msg = SafetyValidator.validate_cleanup_path(config_dir)
    assert valid
    assert msg == ""

def test_symlink_escape_rejected(tmp_path, monkeypatch):
    home = tmp_path / "fakehome"
    config_base = home / ".config"
    config_base.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    # Symlink inside .config pointing outside permitted directories
    escape_target = tmp_path / "secret_data"
    escape_target.mkdir()
    symlink_path = config_base / "evil_link"
    os.symlink(escape_target, symlink_path)

    valid, msg = SafetyValidator.validate_cleanup_path(symlink_path)
    assert not valid
    assert "outside" in msg
