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
        res = run_cmd(["flatpak", "list", "--app", "--columns=application,name,version,installation"])
        if res.returncode != 0:
            return []

        apps: List[ApplicationRecord] = []
        for line in res.stdout.splitlines():
            parts = [p.strip() for p in line.split("\t") if p.strip()]
            if not parts and " " in line:
                parts = [p.strip() for p in line.split() if p.strip()]
            if len(parts) >= 2:
                app_id = parts[0]
                name = parts[1] if len(parts) > 1 else app_id
                version = parts[2] if len(parts) > 3 else "latest"
                scope_str = parts[-1].lower() if len(parts) >= 4 else "system"
                scope = ScopeType.USER if "user" in scope_str else ScopeType.SYSTEM

                apps.append(
                    ApplicationRecord(
                        source=SourceType.FLATPAK,
                        source_scope=scope,
                        package_id=app_id,
                        display_name=name,
                        installed_version=version,
                        install_location=f"/var/lib/flatpak/app/{app_id}" if scope == ScopeType.SYSTEM else f"~/.local/share/flatpak/app/{app_id}",
                    )
                )
        return apps

    def check_updates(self, refresh: bool = False) -> List[UpdateRecord]:
        if not self.is_available():
            return []
        if refresh:
            run_cmd(["flatpak", "update", "--appstream"])

        res = run_cmd(["flatpak", "remote-ls", "--updates", "--columns=application,version"])
        if res.returncode != 0:
            return []

        installed = {app.package_id: app for app in self.list_installed()}
        updates: List[UpdateRecord] = []
        for line in res.stdout.splitlines():
            parts = [p.strip() for p in line.split("\t") if p.strip()]
            if not parts and " " in line:
                parts = [p.strip() for p in line.split() if p.strip()]
            if parts:
                app_id = parts[0]
                new_version = parts[1] if len(parts) > 1 else "latest"
                if app_id in installed:
                    updates.append(UpdateRecord(application=installed[app_id], available_version=new_version))
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
        var_app_dir = Path.home() / ".var" / "app" / target.package_id
        if var_app_dir.exists():
            cleanup_items.append(
                CleanupCandidate(
                    path=var_app_dir,
                    candidate_type="data",
                    evidence=f"Flatpak sandbox data directory matches application ID '{target.package_id}'",
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
