import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
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
                try:
                    entries = list(sdir.iterdir())
                except (OSError, PermissionError):
                    continue
                for f in entries:
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
        if not loc:
            for sdir in self._get_search_dirs():
                if sdir.exists():
                    try:
                        for cand in sdir.iterdir():
                            if cand.is_file() and cand.name.lower().endswith(".appimage"):
                                if cand.stem.lower() == target.package_id.lower():
                                    loc = str(cand.resolve())
                                    break
                    except (OSError, PermissionError):
                        continue
                if loc:
                    break

        app_target = target
        if loc and target.install_location != loc:
            from dataclasses import replace
            app_target = replace(target, install_location=loc)

        native_cmd = ["rm", "-f", loc] if loc else ["true"]
        cleanup_items: List[CleanupCandidate] = []

        if complete:
            # Check for corresponding desktop launcher and config
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            candidates = [
                desktop_dir / f"{target.package_id}.desktop",
                desktop_dir / f"appimagekit-{target.package_id}.desktop",
                Path.home() / ".config" / target.package_id,
            ]
            for cpath in candidates:
                if cpath.exists():
                    cleanup_items.append(
                        CleanupCandidate(
                            path=cpath,
                            candidate_type="desktop_entry" if cpath.suffix == ".desktop" else "config",
                            evidence=f"Associated with AppImage {target.package_id}",
                            confidence=ConfidenceLevel.VERIFIED,
                            estimated_size_bytes=0,
                        )
                    )

        return RemovalPlan(
            application=app_target,
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
        if not loc and len(plan.native_command) >= 3 and plan.native_command[0] == "rm" and plan.native_command[2] != "true":
            loc = plan.native_command[2]
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

    @classmethod
    def get_desktop_dir(cls) -> Path:
        return Path.home() / ".local" / "share" / "applications"

    @classmethod
    def integrate_appimage(cls, appimage_path: Path) -> Tuple[bool, str, Optional[Path]]:
        """Makes AppImage executable, creates an XDG .desktop launcher, and registers with desktop menu."""
        p = Path(appimage_path).expanduser().resolve()
        if not p.is_file():
            return False, f"File not found: {p}", None

        # Ensure executable permissions
        try:
            current_mode = p.stat().st_mode
            p.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as e:
            return False, f"Could not set execute permission on {p.name}: {e}", None

        desktop_dir = cls.get_desktop_dir()
        desktop_dir.mkdir(parents=True, exist_ok=True)

        app_id = p.stem.lower()
        desktop_file = desktop_dir / f"appimage-{app_id}.desktop"

        # Backup existing launcher if collision occurs
        backup_path = None
        if desktop_file.exists():
            backup_file = desktop_dir / f"{desktop_file.name}.backup"
            try:
                shutil.copy2(desktop_file, backup_file)
                backup_path = backup_file
                logger.info("Backed up existing desktop entry to %s", backup_file)
            except Exception as e:
                logger.warning("Could not back up existing desktop entry: %s", e)

        display_name = re.sub(r"[-_]\d+\.\d+.*", "", p.stem).replace("-", " ").title() or app_id

        # Write clean standard .desktop file
        content = f"""[Desktop Entry]
Type=Application
Name={display_name}
Exec="{p}" %U
Icon=application-x-executable
Terminal=false
Categories=Utility;Application;
Comment=Integrated by ULUM
X-AppImage-Version={p.stem}
"""
        try:
            desktop_file.write_text(content, encoding="utf-8")
        except Exception as e:
            return False, f"Failed writing desktop file: {e}", None

        # Update desktop database if utility exists
        if shutil.which("update-desktop-database"):
            try:
                subprocess.run(
                    ["update-desktop-database", str(desktop_dir)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception:
                pass

        return True, f"Successfully integrated '{display_name}' into desktop menu.", desktop_file

    @classmethod
    def unintegrate_appimage(cls, identifier: str) -> Tuple[bool, str]:
        """Removes a generated .desktop launcher and restores backup if present."""
        clean_id = identifier.replace("appimage:", "").replace(".desktop", "").replace("appimage-", "")
        desktop_dir = cls.get_desktop_dir()
        desktop_file = desktop_dir / f"appimage-{clean_id}.desktop"

        if not desktop_file.exists():
            direct_match = desktop_dir / f"{clean_id}.desktop"
            if direct_match.exists():
                desktop_file = direct_match
            else:
                return False, f"Desktop launcher for '{identifier}' not found in {desktop_dir}"

        try:
            desktop_file.unlink()
            backup = desktop_dir / f"{desktop_file.name}.backup"
            if backup.exists():
                shutil.move(backup, desktop_file)
                msg = f"Removed '{desktop_file.name}' and restored previous desktop configuration."
            else:
                msg = f"Successfully unintegrated '{desktop_file.name}' from desktop menu."

            if shutil.which("update-desktop-database"):
                try:
                    subprocess.run(
                        ["update-desktop-database", str(desktop_dir)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                except Exception:
                    pass
            return True, msg
        except Exception as e:
            return False, f"Failed unintegrating {identifier}: {e}"

    @classmethod
    def find_unintegrated_appimages(cls) -> List[Path]:
        """Finds standalone AppImages in common directories that lack a desktop launcher."""
        home = Path.home()
        search_dirs = [
            home / "Downloads",
            home / "Applications",
            home / ".local" / "bin",
            home / "bin",
        ]
        desktop_dir = cls.get_desktop_dir()
        existing_execs = set()

        if desktop_dir.exists():
            for d in desktop_dir.glob("*.desktop"):
                try:
                    for line in d.read_text(encoding="utf-8", errors="ignore").splitlines():
                        if line.startswith("Exec="):
                            raw = line.split("Exec=", 1)[1].strip().split()[0].strip("\"'")
                            existing_execs.add(str(Path(raw).expanduser().resolve()))
                except Exception:
                    pass

        unintegrated: List[Path] = []
        for sdir in search_dirs:
            if sdir.exists():
                try:
                    for cand in sdir.iterdir():
                        if cand.is_file() and cand.name.lower().endswith(".appimage"):
                            resolved = cand.resolve()
                            if str(resolved) not in existing_execs:
                                unintegrated.append(resolved)
                except Exception:
                    pass
        return sorted(list(set(unintegrated)))

    @classmethod
    def integrate_all_unintegrated(cls) -> List[Dict[str, Any]]:
        """Scans and integrates all unintegrated AppImages."""
        cands = cls.find_unintegrated_appimages()
        results = []
        for cand in cands:
            ok, msg, dfile = cls.integrate_appimage(cand)
            results.append({
                "path": str(cand),
                "name": cand.name,
                "success": ok,
                "message": msg,
                "desktop_file": str(dfile) if dfile else None,
            })
        return results
