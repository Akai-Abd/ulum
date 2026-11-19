from pathlib import Path
from typing import Dict, List, Optional, Set
from ulum.adapters.base import BaseAdapter
from ulum.core.models import CleanupCandidate, ConfidenceLevel
from ulum.db.repository import Repository
from ulum.removal.planner import get_dir_size
from ulum.removal.safety import SafetyValidator
from ulum.utils.logging import logger

class LeftoverScanner:
    def __init__(self, repo: Repository, adapters: Optional[Dict[str, BaseAdapter]] = None):
        self.repo = repo
        self.adapters = adapters

    def scan_leftovers(self) -> List[CleanupCandidate]:
        installed = self.repo.get_applications()
        installed_pkg_ids: Set[str] = {app.package_id.lower() for app in installed}
        if not installed_pkg_ids:
            logger.warning("Application inventory is empty. Run 'ulum scan' before scanning for leftovers.")
            return []

        candidates: List[CleanupCandidate] = []
        home = Path.home()

        # 1. Check ~/.var/app (Flatpak data)
        flatpak_data = home / ".var" / "app"
        if flatpak_data.exists():
            flatpak_adp = self.adapters.get("flatpak") if self.adapters else None
            for entry in flatpak_data.iterdir():
                if entry.is_dir() and entry.name.lower() not in installed_pkg_ids:
                    if flatpak_adp and flatpak_adp.is_available() and flatpak_adp.verify_state(entry.name):
                        continue
                    is_valid, _ = SafetyValidator.validate_cleanup_path(entry)
                    if is_valid:
                        candidates.append(
                            CleanupCandidate(
                                path=entry,
                                candidate_type="flatpak_data",
                                evidence=f"Flatpak application ID '{entry.name}' is no longer installed",
                                confidence=ConfidenceLevel.VERIFIED,
                                estimated_size_bytes=get_dir_size(entry),
                            )
                        )

        # 2. Check ~/snap (Snap user data)
        snap_data = home / "snap"
        if snap_data.exists():
            snap_adp = self.adapters.get("snap") if self.adapters else None
            for entry in snap_data.iterdir():
                if entry.is_dir() and entry.name.lower() not in installed_pkg_ids:
                    if snap_adp and snap_adp.is_available() and snap_adp.verify_state(entry.name):
                        continue
                    is_valid, _ = SafetyValidator.validate_cleanup_path(entry)
                    if is_valid:
                        candidates.append(
                            CleanupCandidate(
                                path=entry,
                                candidate_type="snap_data",
                                evidence=f"Snap package '{entry.name}' is no longer installed",
                                confidence=ConfidenceLevel.VERIFIED,
                                estimated_size_bytes=get_dir_size(entry),
                            )
                        )

        # 3. Check ~/.config and ~/.cache
        GENERIC_SYSTEM_DIRS = {
            "dconf", "gtk-3.0", "gtk-4.0", "pulse", "systemd", "autostart",
            "ibus", "fontconfig", "mimeapps.list", "user-dirs.dirs", "menus",
            "cinnamon", "cinnamon-session", "gnome-session", "mate", "xfce4",
            "thumbnails", "pip", "mesa_shader_cache", "evolution", "sounds",
            "nemo", "nautilus", "trash", "gstreamer-1.0", "upower"
        }
        for base, ctype in [(home / ".config", "config"), (home / ".cache", "cache")]:
            if base.exists():
                try:
                    entries = list(base.iterdir())
                except (OSError, PermissionError):
                    continue
                for entry in entries:
                    if entry.is_dir() and not entry.name.startswith("."):
                        name_lower = entry.name.lower()
                        if name_lower in GENERIC_SYSTEM_DIRS:
                            continue
                        if name_lower in installed_pkg_ids or any(
                            pkg.startswith(name_lower) or name_lower.startswith(pkg)
                            for pkg in installed_pkg_ids
                        ):
                            continue
                        is_valid, _ = SafetyValidator.validate_cleanup_path(entry)
                        if is_valid:
                            candidates.append(
                                CleanupCandidate(
                                    path=entry,
                                    candidate_type=ctype,
                                    evidence=f"Directory '{entry.name}' not associated with any active package",
                                    confidence=ConfidenceLevel.PROBABLE,
                                    estimated_size_bytes=get_dir_size(entry),
                                )
                            )

        return candidates
