import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from ulum.adapters.base import BaseAdapter
from ulum.core.models import (
    ApplicationRecord,
    CleanupCandidate,
    ConfidenceLevel,
    ExecutionResult,
    RemovalPlan,
    ScopeType,
    SourceType,
    UpdateRecord,
)

class AppImageAdapter(BaseAdapter):
    @property
    def name(self) -> str:
        return "appimage"

    def is_available(self) -> bool:
        return True

    def _get_search_dirs(self) -> List[Path]:
        home = Path.home()
        return [
            home / "Applications",
            home / ".local" / "bin",
            home / "bin",
        ]

    def list_installed(self) -> List[ApplicationRecord]:
        apps: List[ApplicationRecord] = []
        seen_paths = set()

        # 1. Search directories for .AppImage files
        for sdir in self._get_search_dirs():
            if sdir.exists():
                for f in sdir.iterdir():
                    if f.is_file() and f.name.lower().endswith(".appimage"):
                        seen_paths.add(f.resolve())
                        pkg_id = f.stem.lower()
                        # Extract simple version if present, e.g. AppName-1.2.3.AppImage
                        ver_match = re.search(r"[-_](\d+\.\d+[\w.-]*)", f.stem)
                        version = ver_match.group(1) if ver_match else "standalone"
                        display = re.sub(r"[-_]\d+\.\d+.*", "", f.stem).replace("-", " ").title()

                        apps.append(
                            ApplicationRecord(
                                source=SourceType.APPIMAGE,
                                source_scope=ScopeType.USER,
                                package_id=pkg_id,
                                display_name=display or pkg_id,
                                installed_version=version,
                                install_location=str(f.resolve()),
                            )
                        )

        # 2. Check ~/.local/share/applications/*.desktop for AppImage execs
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        if desktop_dir.exists():
            for dfile in desktop_dir.glob("*.desktop"):
                try:
                    content = dfile.read_text(encoding="utf-8", errors="ignore")
                    for line in content.splitlines():
                        if line.startswith("Exec="):
                            exec_part = line.split("Exec=", 1)[1].strip().split()[0].strip("\"'")
                            p = Path(exec_part).expanduser()
                            if p.exists() and p.name.lower().endswith(".appimage") and p.resolve() not in seen_paths:
                                seen_paths.add(p.resolve())
                                pkg_id = p.stem.lower()
                                apps.append(
                                    ApplicationRecord(
                                        source=SourceType.APPIMAGE,
                                        source_scope=ScopeType.USER,
                                        package_id=pkg_id,
                                        display_name=dfile.stem.replace("-", " ").title(),
                                        installed_version="standalone",
                                        install_location=str(p.resolve()),
                                    )
                                )
                except Exception:
                    pass

        return apps

    def check_updates(self, refresh: bool = False) -> List[UpdateRecord]:
        # Standalone AppImages do not have a unified central repository
        return []

    def build_update_command(self, targets: Optional[Sequence[str]] = None) -> List[str]:
        return []

    def execute_update(self, targets: Optional[Sequence[str]] = None) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            exit_code=0,
            stdout="AppImages manage internal self-updates or manual binary replacement.",
        )

    def build_removal_plan(self, target: ApplicationRecord, complete: bool = False) -> RemovalPlan:
        loc = target.install_location or ""
        native_cmd = ["rm", "-f", loc]
        cleanup_items: List[CleanupCandidate] = []

        if complete:
            # Check for corresponding desktop launcher
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            candidates = [
                desktop_dir / f"{target.package_id}.desktop",
                desktop_dir / f"appimagekit-{target.package_id}.desktop",
            ]
            for cpath in candidates:
                if cpath.exists():
                    cleanup_items.append(
                        CleanupCandidate(
                            path=cpath,
                            candidate_type="desktop_entry",
                            evidence=f"Desktop launcher associated with {target.package_id}",
                            confidence=ConfidenceLevel.VERIFIED,
                            estimated_size_bytes=cpath.stat().st_size,
                        )
                    )

        return RemovalPlan(
            application=target,
            complete=complete,
            native_command=native_cmd,
            packages_to_remove=[target.package_id],
            dependencies_to_remove=[],
            cleanup_items=cleanup_items,
            preserved_items=["User documents"],
            is_safe=True,
        )

    def execute_native_removal(self, plan: RemovalPlan) -> ExecutionResult:
        loc = plan.application.install_location
        if loc and os.path.exists(loc):
            try:
                os.remove(loc)
                return ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=f"Removed AppImage binary: {loc}",
                    removed_items=[loc],
                )
            except Exception as e:
                return ExecutionResult(
                    success=False,
                    exit_code=1,
                    stderr=str(e),
                    error_summary=f"Failed removing {loc}: {e}",
                )
        return ExecutionResult(success=True, exit_code=0, stdout="AppImage binary was already deleted.")

    def get_dependencies(self, package_id: str) -> Dict[str, List[str]]:
        return {"bundled": ["All runtimes and shared libraries are bundled internally in AppImage"]}

    def verify_state(self, package_id: str) -> bool:
        for app in self.list_installed():
            if app.package_id.lower() == package_id.lower():
                return True
        return False
