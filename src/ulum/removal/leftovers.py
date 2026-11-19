from pathlib import Path
from typing import List, Set
from ulum.core.models import CleanupCandidate, ConfidenceLevel
from ulum.db.repository import Repository
from ulum.removal.planner import get_dir_size
from ulum.removal.safety import SafetyValidator

class LeftoverScanner:
    def __init__(self, repo: Repository):
        self.repo = repo

    def scan_leftovers(self) -> List[CleanupCandidate]:
        installed = self.repo.get_applications()
        installed_pkg_ids: Set[str] = {app.package_id.lower() for app in installed}
        candidates: List[CleanupCandidate] = []
        home = Path.home()

        # 1. Check ~/.var/app (Flatpak data)
        flatpak_data = home / ".var" / "app"
        if flatpak_data.exists():
            for entry in flatpak_data.iterdir():
                if entry.is_dir() and entry.name.lower() not in installed_pkg_ids:
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
            for entry in snap_data.iterdir():
                if entry.is_dir() and entry.name.lower() not in installed_pkg_ids:
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
        for base, ctype in [(home / ".config", "config"), (home / ".cache", "cache")]:
            if base.exists():
                for entry in base.iterdir():
                    if entry.is_dir():
                        name_lower = entry.name.lower()
                        if name_lower not in installed_pkg_ids and "." in entry.name:
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
