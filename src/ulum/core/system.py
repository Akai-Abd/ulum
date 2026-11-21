import os
import platform
from pathlib import Path
from typing import Dict
from ulum.core.models import SystemInfo
from ulum.utils.process import command_exists

SUPPORTED_DISTROS = {
    "linuxmint": ["22", "22.1", "22.2"],
    "ubuntu": ["24.04", "24.04.1", "24.04.2", "24.04.3"],
}

def parse_os_release(path: Path = Path("/etc/os-release")) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip("\"'")
            data[k] = v
    return data

def get_system_info(os_release_path: Path = Path("/etc/os-release")) -> SystemInfo:
    info = parse_os_release(os_release_path)
    distro_id = info.get("ID", platform.system().lower())
    distro_name = info.get("NAME", platform.system())
    distro_version = info.get("VERSION_ID", platform.release())

    supported_versions = SUPPORTED_DISTROS.get(distro_id, [])
    is_supported = any(distro_version.startswith(v) for v in supported_versions)

    return SystemInfo(
        distro_id=distro_id,
        distro_name=distro_name,
        distro_version=distro_version,
        arch=platform.machine(),
        kernel=platform.release(),
        is_supported=is_supported,
    )

def detect_package_managers() -> Dict[str, bool]:
    return {
        "apt": command_exists("apt-get") and command_exists("dpkg-query"),
        "flatpak": command_exists("flatpak"),
        "snap": command_exists("snap"),
        "appimage": True,
    }


