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

class SnapAdapter(BaseAdapter):
    @property
    def name(self) -> str:
        return "snap"

    def is_available(self) -> bool:
        return command_exists("snap")

    def list_installed(self) -> List[ApplicationRecord]:
        if not self.is_available():
            return []
        res = run_cmd(["snap", "list"])
        if res.returncode != 0:
            return []

        apps: List[ApplicationRecord] = []
        lines = res.stdout.splitlines()
        if len(lines) <= 1:
            return []

        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2:
                name, version = parts[0], parts[1]
                apps.append(
                    ApplicationRecord(
                        source=SourceType.SNAP,
                        source_scope=ScopeType.SYSTEM,
                        package_id=name,
                        display_name=name,
                        installed_version=version,
                        install_location=f"/snap/{name}",
                    )
                )
        return apps

    def check_updates(self, refresh: bool = False) -> List[UpdateRecord]:
        if not self.is_available():
            return []
        res = run_cmd(["snap", "refresh", "--list"])
        if res.returncode != 0:
            return []

        installed = {app.package_id: app for app in self.list_installed()}
        updates: List[UpdateRecord] = []
        lines = res.stdout.splitlines()
        if len(lines) <= 1:
            return []

        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2:
                name, new_ver = parts[0], parts[1]
                if name in installed:
                    updates.append(UpdateRecord(application=installed[name], available_version=new_ver))
        return updates

    def build_update_command(self, targets: Optional[Sequence[str]] = None) -> List[str]:
        cmd = ["snap", "refresh"]
        if targets:
            cmd.extend(targets)
        return cmd

    def execute_update(self, targets: Optional[Sequence[str]] = None) -> ExecutionResult:
        cmd = self.build_update_command(targets)
        res = run_cmd(cmd, require_root=True)
        return ExecutionResult(
            success=(res.returncode == 0),
            exit_code=res.returncode,
            stdout=res.stdout,
            stderr=res.stderr,
            error_summary=res.stderr if res.returncode != 0 else None,
        )

    def build_removal_plan(self, target: ApplicationRecord, complete: bool = False) -> RemovalPlan:
        cmd = ["snap", "remove"]
        if complete:
            cmd.append("--purge")
        cmd.append(target.package_id)

        cleanup_items: List[CleanupCandidate] = []
        snap_user_dir = Path.home() / "snap" / target.package_id
        if snap_user_dir.exists():
            cleanup_items.append(
                CleanupCandidate(
                    path=snap_user_dir,
                    candidate_type="data",
                    evidence=f"User snap directory matches snap package '{target.package_id}'",
                    confidence=ConfidenceLevel.VERIFIED,
                )
            )

        return RemovalPlan(
            application=target,
            complete=complete,
            native_command=cmd,
            packages_to_remove=[target.package_id],
            dependencies_to_remove=[],
            cleanup_items=cleanup_items,
            preserved_items=["Snap snapshot revisions (unless purged)"],
            is_safe=True,
        )

    def execute_native_removal(self, plan: RemovalPlan) -> ExecutionResult:
        res = run_cmd(plan.native_command, require_root=True)
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
        res = run_cmd(["snap", "info", package_id])
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.strip().startswith("base:"):
                    deps.append(line.split("base:", 1)[1].strip())
        return {"base": deps}

    def verify_state(self, package_id: str) -> bool:
        res = run_cmd(["snap", "list", package_id])
        return res.returncode == 0
