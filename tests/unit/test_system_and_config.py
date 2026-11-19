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
