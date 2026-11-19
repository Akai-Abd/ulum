import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

def get_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "ulum"

@dataclass
class UlumConfig:
    enabled_adapters: List[str] = field(default_factory=lambda: ["apt", "flatpak", "snap"])
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
            enabled_adapters=data.get("enabled_adapters", ["apt", "flatpak", "snap"]),
            excluded_packages=data.get("excluded_packages", []),
            require_confirmation=data.get("require_confirmation", True),
            log_level=data.get("log_level", "INFO"),
        )
    except Exception:
        return UlumConfig()
