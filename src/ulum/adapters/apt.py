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

class AptAdapter(BaseAdapter):
    @property
    def name(self) -> str:
        return "apt"

    def is_available(self) -> bool:
        return command_exists("apt-get") and command_exists("dpkg-query")

    def list_installed(self) -> List[ApplicationRecord]:
        if not self.is_available():
            return []
        res = run_cmd(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"])
        if res.returncode != 0:
            return []

        apps: List[ApplicationRecord] = []
        for line in res.stdout.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 3 and parts[2] == "install ok installed":
                pkg_name, version = parts[0], parts[1]
                apps.append(
                    ApplicationRecord(
                        source=SourceType.APT,
                        source_scope=ScopeType.SYSTEM,
                        package_id=pkg_name,
                        display_name=pkg_name,
                        installed_version=version,
                        install_location="/usr",
                    )
                )
        return apps

    def check_updates(self, refresh: bool = False) -> List[UpdateRecord]:
        if not self.is_available():
            return []
        if refresh:
            run_cmd(["apt-get", "update"], require_root=True)

        res = run_cmd(["apt-get", "-s", "dist-upgrade"])
        if res.returncode != 0:
            return []

        installed_map = {app.package_id: app for app in self.list_installed()}
        updates: List[UpdateRecord] = []

        # Inst package [current_version] (new_version arch)
        pattern = re.compile(r"^Inst\s+([^\s]+)(?:\s+\[([^\]]+)\])?\s+\((?:([^,\s]+))")
        for line in res.stdout.splitlines():
            line = line.strip()
            m = pattern.match(line)
            if m:
                pkg_id = m.group(1)
                cur_ver = m.group(2) or (installed_map[pkg_id].installed_version if pkg_id in installed_map else "unknown")
                new_ver = m.group(3) or "unknown"
                app = installed_map.get(
                    pkg_id,
                    ApplicationRecord(
                        source=SourceType.APT,
                        source_scope=ScopeType.SYSTEM,
                        package_id=pkg_id,
                        display_name=pkg_id,
                        installed_version=cur_ver,
                    ),
                )
                updates.append(UpdateRecord(application=app, available_version=new_ver))
        return updates

    def build_update_command(self, targets: Optional[Sequence[str]] = None) -> List[str]:
        dpkg_opts = ["-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold"]
        if targets:
            return ["apt-get", "install", "--only-upgrade", "-y"] + dpkg_opts + list(targets)
        return ["apt-get", "dist-upgrade", "-y"] + dpkg_opts

    def execute_update(self, targets: Optional[Sequence[str]] = None) -> ExecutionResult:
        cmd = self.build_update_command(targets)
        res = run_cmd(cmd, require_root=True, env={"DEBIAN_FRONTEND": "noninteractive"})
        return ExecutionResult(
            success=(res.returncode == 0),
            exit_code=res.returncode,
            stdout=res.stdout,
            stderr=res.stderr,
            error_summary=res.stderr if res.returncode != 0 else None,
        )

    def build_removal_plan(self, target: ApplicationRecord, complete: bool = False) -> RemovalPlan:
        native_cmd = (
            ["apt-get", "purge", "-y", target.package_id]
            if complete
            else ["apt-get", "remove", "-y", target.package_id]
        )
        packages_to_remove = [target.package_id]
        dependencies_to_remove: List[str] = []
        safety_warnings: List[str] = []
        has_critical_rdeps = False

        # Check reverse dependencies
        rdep_res = run_cmd(["apt-cache", "rdepends", "--installed", target.package_id])
        if rdep_res.returncode == 0:
            lines = [l.strip() for l in rdep_res.stdout.splitlines() if l.strip() and not l.startswith(target.package_id)]
            rdeps = [l for l in lines if not l.startswith("<") and not l.endswith(":")]
            if rdeps:
                has_critical_rdeps = True
                safety_warnings.append(
                    f"Warning: {len(rdeps)} installed package(s) depend on {target.package_id}: {', '.join(rdeps[:5])}"
                )

        cleanup_items: List[CleanupCandidate] = []
        if complete:
            home = Path.home()
            user_candidates = [
                (home / ".config" / target.package_id, "config"),
                (home / ".cache" / target.package_id, "cache"),
                (home / ".local" / "share" / target.package_id, "data"),
            ]
            for path, ctype in user_candidates:
                if path.exists():
                    cleanup_items.append(
                        CleanupCandidate(
                            path=path,
                            candidate_type=ctype,
                            evidence=f"Directory matches package name '{target.package_id}'",
                            confidence=ConfidenceLevel.VERIFIED,
                        )
                    )

        return RemovalPlan(
            application=target,
            complete=complete,
            native_command=native_cmd,
            packages_to_remove=packages_to_remove,
            dependencies_to_remove=dependencies_to_remove,
            cleanup_items=cleanup_items,
            preserved_items=["Personal documents in ~", "/etc/systemd/*"],
            safety_warnings=safety_warnings,
            is_safe=(not has_critical_rdeps and len(safety_warnings) == 0),
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
        deps: List[str] = []
        rdeps: List[str] = []
        res_dep = run_cmd(["apt-cache", "depends", package_id])
        if res_dep.returncode == 0:
            for line in res_dep.stdout.splitlines():
                line = line.strip()
                if line.startswith("Depends:"):
                    deps.append(line.split("Depends:", 1)[1].strip())

        res_rdep = run_cmd(["apt-cache", "rdepends", "--installed", package_id])
        if res_rdep.returncode == 0:
            for line in res_rdep.stdout.splitlines():
                line = line.strip()
                if line and not line.startswith(package_id) and not line.endswith(":"):
                    rdeps.append(line)

        return {"depends": deps, "rdepends": rdeps}

    def verify_state(self, package_id: str) -> bool:
        res = run_cmd(["dpkg-query", "-W", "-f=${Status}", package_id])
        return res.returncode == 0 and "install ok installed" in res.stdout

    def get_download_size(self) -> int:
        """Estimates total download size in bytes for pending upgrades."""
        if not self.is_available():
            return 0
        res = run_cmd(["apt-get", "-s", "dist-upgrade"])
        ret = getattr(res, "returncode", getattr(res, "exit_code", 0))
        if ret != 0 or not getattr(res, "stdout", None):
            return 0
        m = re.search(r"Need to get\s+([\d.,]+)\s*([kKMGT]?B)", res.stdout, re.IGNORECASE)
        if not m:
            return 0
        num_str = m.group(1).replace(",", "")
        unit = m.group(2).upper()
        multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
        try:
            return int(float(num_str) * multipliers.get(unit, 1))
        except ValueError:
            return 0
