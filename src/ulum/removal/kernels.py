import os
import platform
import re
import shutil
from typing import Any, Dict, List, Optional, Set
from ulum.cli.display import format_bytes
from ulum.core.models import ExecutionResult
from ulum.utils.logging import logger
from ulum.utils.process import command_exists, run_cmd


class KernelCleaner:
    """Detects and safely removes obsolete Linux kernels while protecting running and fallback kernels."""

    @staticmethod
    def get_running_kernel() -> str:
        try:
            rel = os.uname().release
            return rel if rel else "unknown"
        except Exception:
            return platform.release() or "unknown"

    @classmethod
    def detect_snapshot_tool(cls) -> Optional[str]:
        """Detects available snapshot tools on the system."""
        if shutil.which("timeshift"):
            return "timeshift"
        if shutil.which("snapper"):
            return "snapper"
        if shutil.which("btrfs"):
            return "btrfs"
        return None

    @classmethod
    def check_dkms_modules(cls) -> List[str]:
        """Checks for active DKMS kernel modules."""
        if not command_exists("dkms"):
            return []
        try:
            res = run_cmd(["dkms", "status"])
            if res.returncode == 0 and res.stdout:
                return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            pass
        return []

    @classmethod
    def list_kernel_packages(cls) -> List[Dict[str, str]]:
        """Queries dpkg for installed and lingering kernel packages."""
        if not command_exists("dpkg-query"):
            return []

        cmd = [
            "dpkg-query",
            "-W",
            "-f=${Package}\t${Version}\t${Status}\t${Installed-Size}\n",
            "linux-image-[0-9]*",
            "linux-headers-[0-9]*",
            "linux-modules-[0-9]*",
            "linux-modules-extra-[0-9]*",
        ]
        res = run_cmd(cmd)
        if res.returncode != 0 and not res.stdout:
            return []

        packages = []
        for line in res.stdout.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                pkg = parts[0].strip()
                ver = parts[1].strip()
                status = parts[2].strip()
                size_kb = int(parts[3].strip()) if len(parts) >= 4 and parts[3].strip().isdigit() else 0
                packages.append({
                    "package": pkg,
                    "version": ver,
                    "status": status,
                    "size_bytes": size_kb * 1024,
                })
        return packages

    @classmethod
    def _extract_release(cls, pkg_name: str) -> Optional[str]:
        """Extracts the kernel release (e.g. 6.8.0-149-generic or 6.8.0-149) from package name."""
        # linux-image-6.8.0-149-generic -> 6.8.0-149-generic
        # linux-headers-6.8.0-149 -> 6.8.0-149
        m = re.search(r"linux-(?:image|headers|modules|modules-extra)-([\d.]+-[\w-]+)", pkg_name)
        if m:
            return m.group(1)
        m2 = re.search(r"linux-(?:image|headers|modules|modules-extra)-([\d.]+)", pkg_name)
        if m2:
            return m2.group(1)
        return None

    @classmethod
    def plan_cleanup(cls) -> Dict[str, Any]:
        """Builds a kernel cleanup plan preserving the active and latest fallback kernel."""
        running = cls.get_running_kernel()
        if not running or running == "unknown":
            return {
                "running_kernel": "unknown",
                "kept_kernels": [],
                "removable_kernels": [],
                "packages_to_remove": [],
                "residual_packages": [],
                "estimated_freed_bytes": 0,
                "formatted_freed": "0 B",
                "is_safe": False,
                "safety_error": "Cannot detect running kernel release. Aborting cleanup.",
            }

        raw_pkgs = cls.list_kernel_packages()

        # Group installed image packages by release
        installed_images: Set[str] = set()
        installed_releases: Dict[str, List[Dict[str, Any]]] = {}
        residual_pkgs: List[Dict[str, Any]] = []

        for p in raw_pkgs:
            status = p["status"]
            rel = cls._extract_release(p["package"])
            if not rel:
                continue

            if "install ok installed" in status:
                installed_releases.setdefault(rel, []).append(p)
                if p["package"].startswith("linux-image-"):
                    installed_images.add(rel)
            elif "config-files" in status:
                residual_pkgs.append(p)

        # Sort installed releases (version sorting using simple tuple of ints)
        def release_key(rel_str: str):
            nums = [int(n) for n in re.findall(r"\d+", rel_str)]
            return nums

        sorted_releases = sorted(installed_releases.keys(), key=release_key)

        # Active kernel must NEVER be removed
        kept_releases: Set[str] = set()
        for r in sorted_releases:
            if r == running or running.startswith(r) or r.startswith(running.split("-")[0]):
                if r == running or f"{r}-generic" == running or running.startswith(r):
                    kept_releases.add(r)

        kept_releases.add(running)

        # Also keep the newest installed non-running release as fallback (enforcing 2-kernel minimum)
        non_running_installed = [r for r in sorted_releases if r not in kept_releases]
        if non_running_installed:
            latest_fallback = non_running_installed[-1]
            kept_releases.add(latest_fallback)

        packages_to_remove: List[str] = []
        removable_releases: List[str] = []
        total_freed_bytes = 0

        for r in sorted_releases:
            if r not in kept_releases:
                removable_releases.append(r)
                for p in installed_releases[r]:
                    packages_to_remove.append(p["package"])
                    total_freed_bytes += p.get("size_bytes", 0)

        # Include lingering residual config files
        for p in residual_pkgs:
            packages_to_remove.append(p["package"])
            total_freed_bytes += p.get("size_bytes", 0)

        # If dpkg sizes were 0, approximate ~400MB per full kernel removed
        if total_freed_bytes == 0 and removable_releases:
            total_freed_bytes = len(removable_releases) * 450 * 1024 * 1024

        # Check DKMS modules
        dkms_modules = cls.check_dkms_modules()
        dkms_warnings = []
        for mod in dkms_modules:
            for rem in removable_releases:
                if rem in mod:
                    dkms_warnings.append(f"DKMS module '{mod}' references removable kernel {rem}")

        # Check snapshot tool
        snapshot_tool = cls.detect_snapshot_tool()

        # 2-kernel minimum guard: if total installed kernel count would drop below 2
        total_images = len(installed_images) if installed_images else len(installed_releases)
        leaves_fewer_than_two = total_images > 1 and len(kept_releases) < 2

        is_safe = (
            running not in removable_releases
            and len(packages_to_remove) > 0
            and not leaves_fewer_than_two
        )

        return {
            "running_kernel": running,
            "kept_kernels": sorted(list(kept_releases)),
            "removable_kernels": removable_releases,
            "packages_to_remove": packages_to_remove,
            "residual_packages": [p["package"] for p in residual_pkgs],
            "estimated_freed_bytes": total_freed_bytes,
            "formatted_freed": format_bytes(total_freed_bytes),
            "snapshot_tool": snapshot_tool,
            "snapshot_recommended": snapshot_tool is not None,
            "dkms_warnings": dkms_warnings,
            "is_safe": is_safe,
        }

    @classmethod
    def execute_cleanup(cls, plan: Dict[str, Any], dry_run: bool = False) -> ExecutionResult:
        """Executes purge of unneeded kernel packages."""
        if not plan.get("is_safe", True) and not dry_run:
            return ExecutionResult(
                success=False,
                exit_code=1,
                stderr=plan.get("safety_error", "Plan rejected by safety guard: cannot guarantee 2 surviving kernels."),
                error_summary="Aborted: safety guard rejected kernel plan",
            )

        pkgs = plan.get("packages_to_remove", [])
        if not pkgs:
            return ExecutionResult(success=True, exit_code=0, stdout="No obsolete kernels to remove.")

        running = plan.get("running_kernel") or cls.get_running_kernel()
        # Double check safety guard
        for p in pkgs:
            if running in p:
                return ExecutionResult(
                    success=False,
                    exit_code=1,
                    stderr=f"Refusing to remove package matching running kernel: {p}",
                    error_summary="Aborted: running kernel detected in removal list",
                )

        if dry_run:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"Dry-run: would purge {len(pkgs)} kernel packages: {' '.join(pkgs)}",
                removed_items=pkgs,
            )

        cmd = ["apt-get", "purge", "-y"] + pkgs
        logger.info("Purging %d obsolete kernel packages...", len(pkgs))
        res = run_cmd(cmd, require_root=True, env={"DEBIAN_FRONTEND": "noninteractive"})

        err_summary = None
        if res.returncode != 0:
            err_summary = (
                f"CRITICAL WARNING: Kernel purge failed halfway (exit code {res.returncode})! "
                "Do NOT reboot until fixed. Run 'sudo apt-get install -f' or reinstall kernel."
            )
            logger.error(err_summary)

        return ExecutionResult(
            success=(res.returncode == 0),
            exit_code=res.returncode,
            stdout=res.stdout,
            stderr=res.stderr,
            removed_items=pkgs if res.returncode == 0 else [],
            error_summary=err_summary or (res.stderr if res.returncode != 0 else None),
        )
