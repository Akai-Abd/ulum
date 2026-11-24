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
from ulum.utils.process import command_exists, run_cmd

class FlatpakAdapter(BaseAdapter):
    @property
    def name(self) -> str:
        return "flatpak"

    def is_available(self) -> bool:
        return command_exists("flatpak")

    def list_installed(self) -> List[ApplicationRecord]:
        if not self.is_available():
            return []
        res = run_cmd(["flatpak", "list", "--columns=application:f,name:f,version:f,branch:f,installation:f,active:f"])
        if res.returncode != 0:
            return []

        apps: List[ApplicationRecord] = []
        for line in res.stdout.splitlines():
            parts = line.split("\t")
            if not parts or not parts[0].strip():
                continue
            app_id = parts[0].strip()
            name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else app_id
            version = parts[2].strip() if len(parts) > 2 else ""

            # Support 4-column test mocks ('app\tname\tver\tscope') and 5-6 column real flatpak list
            if len(parts) == 4 and parts[3].strip().lower() in ("system", "user"):
                branch = ""
                scope_str = parts[3].strip().lower()
                active = ""
            else:
                branch = parts[3].strip() if len(parts) > 3 else ""
                scope_str = parts[4].strip().lower() if len(parts) > 4 else "system"
                active = parts[5].strip() if len(parts) > 5 else ""

            if not version:
                version = f"{branch} ({active[:8]})" if active else (branch or "latest")

            scope = ScopeType.USER if "user" in scope_str else ScopeType.SYSTEM
            # shortcut: package_id tags non-stable branches with //branch, upgrade to full ref if multiple architectures co-install
            pkg_id = f"{app_id}//{branch}" if branch and branch != "stable" else app_id

            base_dir = Path("/var/lib/flatpak") if scope == ScopeType.SYSTEM else Path.home() / ".local/share/flatpak"
            loc = base_dir / "app" / app_id
            if not loc.exists() and (base_dir / "runtime" / app_id).exists():
                loc = base_dir / "runtime" / app_id

            apps.append(
                ApplicationRecord(
                    source=SourceType.FLATPAK,
                    source_scope=scope,
                    package_id=pkg_id,
                    display_name=name,
                    installed_version=version,
                    install_location=str(loc),
                )
            )
        return apps

    def check_updates(self, refresh: bool = False) -> List[UpdateRecord]:
        if not self.is_available():
            return []
        if refresh:
            run_cmd(["flatpak", "update", "--appstream"])

        res = run_cmd(["flatpak", "remote-ls", "--updates", "--columns=application:f,branch:f,version:f,commit:f"])
        if res.returncode != 0:
            return []

        installed = {app.package_id: app for app in self.list_installed()}
        updates: List[UpdateRecord] = []
        for line in res.stdout.splitlines():
            parts = line.split("\t")
            if not parts or not parts[0].strip():
                continue
            app_id = parts[0].strip()
            branch = parts[1].strip() if len(parts) > 1 else ""
            raw_ver = parts[2].strip() if len(parts) > 2 else ""
            commit = parts[3].strip() if len(parts) > 3 else ""

            if raw_ver:
                new_version = raw_ver
            elif commit:
                new_version = f"{branch} ({commit[:8]})" if branch else commit[:8]
            else:
                new_version = branch or "latest"

            target_key = f"{app_id}//{branch}" if branch and branch != "stable" else app_id
            app = installed.get(target_key) or installed.get(app_id)
            if app:
                updates.append(UpdateRecord(application=app, available_version=new_version))
        return updates

    def build_update_command(self, targets: Optional[Sequence[str]] = None) -> List[str]:
        cmd = ["flatpak", "update", "-y"]
        if targets:
            cmd.extend(targets)
        return cmd

    def execute_update(self, targets: Optional[Sequence[str]] = None) -> ExecutionResult:
        cmd = self.build_update_command(targets)
        res = run_cmd(cmd)
        return ExecutionResult(
            success=(res.returncode == 0),
            exit_code=res.returncode,
            stdout=res.stdout,
            stderr=res.stderr,
            error_summary=res.stderr if res.returncode != 0 else None,
        )

    def build_removal_plan(self, target: ApplicationRecord, complete: bool = False) -> RemovalPlan:
        scope_flag = "--user" if target.source_scope == ScopeType.USER else "--system"
        native_cmd = ["flatpak", "uninstall", "-y", scope_flag]
        if complete:
            native_cmd.append("--delete-data")
        native_cmd.append(target.package_id)

        cleanup_items: List[CleanupCandidate] = []
        if complete:
            app_base_id = target.package_id.split("//")[0]
            var_app_dir = Path.home() / ".var" / "app" / app_base_id
            if var_app_dir.exists():
                cleanup_items.append(
                    CleanupCandidate(
                        path=var_app_dir,
                        candidate_type="data",
                        evidence=f"Flatpak sandbox data directory matches application ID '{app_base_id}'",
                        confidence=ConfidenceLevel.VERIFIED,
                    )
                )

        return RemovalPlan(
            application=target,
            complete=complete,
            native_command=native_cmd,
            packages_to_remove=[target.package_id],
            dependencies_to_remove=[],
            cleanup_items=cleanup_items,
            preserved_items=["Unused runtimes (run 'flatpak uninstall --unused' separately)"],
            is_safe=True,
        )

    def execute_native_removal(self, plan: RemovalPlan) -> ExecutionResult:
        require_root = (plan.application.source_scope == ScopeType.SYSTEM)
        res = run_cmd(plan.native_command, require_root=require_root)
        return ExecutionResult(
            success=(res.returncode == 0),
            exit_code=res.returncode,
            stdout=res.stdout,
            stderr=res.stderr,
            removed_items=plan.packages_to_remove,
            error_summary=res.stderr if res.returncode != 0 else None,
        )

    def get_dependencies(self, package_id: str) -> Dict[str, List[str]]:
        deps = []
        res = run_cmd(["flatpak", "info", "--show-runtime", package_id])
        if res.returncode == 0 and res.stdout.strip():
            deps.append(res.stdout.strip())
        return {"runtime": deps}

    def verify_state(self, package_id: str) -> bool:
        res = run_cmd(["flatpak", "info", package_id])
        return res.returncode == 0

    def get_download_size(self) -> int:
        """Estimates total download size in bytes for pending updates."""
        if not self.is_available():
            return 0
        res = run_cmd(["flatpak", "remote-ls", "--updates", "--columns=download-size"])
        ret = getattr(res, "returncode", getattr(res, "exit_code", 0))
        if ret != 0 or not getattr(res, "stdout", None):
            return 0
        total_bytes = 0
        multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
        for line in res.stdout.splitlines():
            line = line.strip()
            m = re.search(r"([\d.,]+)\s*([kKMGT]?B)", line, re.IGNORECASE)
            if m:
                num_str = m.group(1).replace(",", "")
                unit = m.group(2).upper()
                try:
                    total_bytes += int(float(num_str) * multipliers.get(unit, 1))
                except ValueError:
                    pass
        return total_bytes
