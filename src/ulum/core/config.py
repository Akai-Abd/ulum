import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

def get_config_dir() -> Path:
    pkexec_uid = os.environ.get("PKEXEC_UID")
    real_user = os.environ.get("SUDO_USER")
    if pkexec_uid:
        try:
            import pwd
            base = Path(pwd.getpwuid(int(pkexec_uid)).pw_dir) / ".config"
        except Exception:
            base = Path.home() / ".config"
    elif real_user:
        try:
            import pwd
            base = Path(pwd.getpwnam(real_user).pw_dir) / ".config"
        except Exception:
            base = Path.home() / ".config"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "ulum"

@dataclass
class UlumConfig:
    enabled_adapters: List[str] = field(default_factory=lambda: ["apt", "flatpak", "snap", "appimage"])
    excluded_packages: List[str] = field(default_factory=list)
    require_confirmation: bool = True
    log_level: str = "INFO"

def load_config(config_path: Path | None = None) -> UlumConfig:
    path = config_path or (get_config_dir() / "config.toml")
    if not path.exists():
        return UlumConfig()

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return UlumConfig(
            enabled_adapters=data.get("enabled_adapters", ["apt", "flatpak", "snap", "appimage"]),
            excluded_packages=data.get("excluded_packages", []),
            require_confirmation=data.get("require_confirmation", True),
            log_level=str(data.get("log_level", "INFO")).upper(),
        )
    except Exception:
        return UlumConfig()

def save_config(config: UlumConfig, config_path: Path | None = None) -> None:
    path = config_path or (get_config_dir() / "config.toml")
    path.parent.mkdir(parents=True, exist_ok=True)
    adapters_str = ", ".join(f'"{a}"' for a in config.enabled_adapters)
    excluded_str = ", ".join(f'"{p}"' for p in config.excluded_packages)
    content = f"""# ULUM Configuration
enabled_adapters = [{adapters_str}]
excluded_packages = [{excluded_str}]
require_confirmation = {str(config.require_confirmation).lower()}
log_level = "{config.log_level}"
"""
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)
