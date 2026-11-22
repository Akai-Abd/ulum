"""System Health Diagnostics and Doctor module for ULUM v0.4."""
import json
import logging
import os
import platform
import re
import shutil
import sqlite3
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ulum.core.system import detect_package_managers, get_system_info
from ulum.db.database import get_db_path, init_db
from ulum.db.repository import Repository
from ulum.doctor.repos import AptRepoDoctor
from ulum.removal.kernels import KernelCleaner
from ulum.utils.process import command_exists, is_root, run_cmd
from ulum.utils.self_update import SelfUpdater

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    name: str
    title: str
    status: str  # "ok", "warn", "fail"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DoctorReport:
    timestamp: str
    overall_status: str  # "healthy", "degraded", "failed"
    exit_code: int
    failing_checks: List[str]
    checks: List[HealthCheckResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "overall_status": self.overall_status,
            "exit_code": self.exit_code,
            "failing_checks": self.failing_checks,
            "checks": [asdict(c) for c in self.checks],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class SystemDoctor:
    """Performs the comprehensive 8-point ULUM health checklist."""

    @classmethod
    def check_distribution(cls) -> HealthCheckResult:
        info = get_system_info()
        status = "ok" if info.is_supported else "warn"
        msg = f"{info.distro_name} {info.distro_version} ({info.arch}, Linux {info.kernel})"
        if not info.is_supported:
            msg += " [Untested/Experimental Distribution]"
        else:
            msg += " [Supported]"
        return HealthCheckResult(
            name="distribution",
            title="Distribution & Kernel",
            status=status,
            message=msg,
            details={
                "distro_id": info.distro_id,
                "distro_name": info.distro_name,
                "distro_version": info.distro_version,
                "arch": info.arch,
                "kernel": info.kernel,
                "is_supported": info.is_supported,
            },
        )

    @classmethod
    def check_package_managers(cls) -> HealthCheckResult:
        mgrs = detect_package_managers()
        avail = [name.upper() for name, ok in mgrs.items() if ok]
        if not avail:
            status = "fail"
            msg = "No package managers detected on this system"
        elif not mgrs.get("apt", False):
            status = "warn"
            msg = f"Available: {', '.join(avail)} (APT missing on Debian/Ubuntu base)"
        else:
            status = "ok"
            msg = f"Available: {', '.join(avail)}"

        return HealthCheckResult(
            name="package_managers",
            title="Package Managers",
            status=status,
            message=msg,
            details=mgrs,
        )

    @classmethod
    def check_repositories(cls, live_network: bool = False) -> HealthCheckResult:
        sources_list = Path("/etc/apt/sources.list")
        sources_dir = Path("/etc/apt/sources.list.d")

        source_files_count = 0
        active_entries_count = 0
        disabled_by_ulum = 0

        if sources_list.exists():
            source_files_count += 1
            try:
                for line in sources_list.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line.startswith("# DISABLED BY ULUM"):
                        disabled_by_ulum += 1
                    elif line and not line.startswith("#"):
                        active_entries_count += 1
            except Exception:
                pass

        if sources_dir.exists():
            for p in sources_dir.glob("*.list"):
                source_files_count += 1
                try:
                    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if line.startswith("# DISABLED BY ULUM"):
                            disabled_by_ulum += 1
                        elif line and not line.startswith("#"):
                            active_entries_count += 1
                except Exception:
                    pass
            for p in sources_dir.glob("*.sources"):
                source_files_count += 1
                try:
                    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if line.startswith("# DISABLED BY ULUM"):
                            disabled_by_ulum += 1
                        elif line and not line.startswith("#"):
                            active_entries_count += 1
                except Exception:
                    pass

        # If live_network requested and root available, scan for 404s
        broken_entries: List[Dict[str, Any]] = []
        if live_network and (is_root() or command_exists("sudo")):
            try:
                broken_entries, _ = AptRepoDoctor.check_broken_sources()
            except Exception as e:
                logger.debug("Failed checking broken sources: %s", e)

        if broken_entries:
            status = "fail"
            msg = f"{len(broken_entries)} broken/404 repository source(s) detected. Run 'ulum doctor --fix-repos'."
        elif disabled_by_ulum > 0:
            status = "warn"
            msg = f"{active_entries_count} active sources across {source_files_count} files ({disabled_by_ulum} disabled by ULUM)"
        else:
            status = "ok"
            msg = f"{active_entries_count} active sources across {source_files_count} files"

        return HealthCheckResult(
            name="repositories",
            title="Repository Health",
            status=status,
            message=msg,
            details={
                "source_files_count": source_files_count,
                "active_entries_count": active_entries_count,
                "disabled_by_ulum": disabled_by_ulum,
                "broken_entries_count": len(broken_entries),
                "broken_entries": broken_entries,
            },
        )

    @classmethod
    def check_boot_health(cls) -> HealthCheckResult:
        boot_path = Path("/boot")
        target_path = boot_path if boot_path.exists() else Path("/")
        try:
            usage = shutil.disk_usage(str(target_path))
            free_mb = usage.free / (1024 * 1024)
            total_mb = usage.total / (1024 * 1024)
            free_pct = (usage.free / usage.total) * 100
        except Exception:
            free_mb = 0.0
            total_mb = 0.0
            free_pct = 0.0

        booted_kernel = KernelCleaner.get_running_kernel()
        kernels = KernelCleaner.list_kernel_packages()
        kernel_count = len(kernels)

        if free_mb > 0 and free_mb < 100:
            status = "fail"
            msg = f"Critically low disk space on /boot: {free_mb:.1f} MB remaining ({free_pct:.1f}% free). Purge old kernels with 'ulum cleanup --kernels'!"
        elif free_mb > 0 and free_mb < 250:
            status = "warn"
            msg = f"Low disk space on /boot: {free_mb:.1f} MB free ({free_pct:.1f}%), {kernel_count} kernels installed (Booted: {booted_kernel})"
        else:
            status = "ok"
            msg = f"{free_mb:.0f} MB free ({free_pct:.1f}%), {kernel_count} kernels installed (Booted: {booted_kernel})"

        return HealthCheckResult(
            name="boot_health",
            title="/boot Partition & Kernel Health",
            status=status,
            message=msg,
            details={
                "free_mb": round(free_mb, 1),
                "total_mb": round(total_mb, 1),
                "free_percent": round(free_pct, 1),
                "installed_kernels_count": kernel_count,
                "booted_kernel": booted_kernel,
            },
        )

    @classmethod
    def check_database(cls, db_path: Optional[Path] = None) -> HealthCheckResult:
        target = db_path if db_path is not None else get_db_path()
        if not target.exists():
            # If not yet created, test writable directory
            parent = target.parent
            if parent.exists() and os.access(parent, os.W_OK):
                return HealthCheckResult(
                    name="database",
                    title="Database Storage",
                    status="ok",
                    message=f"{target} (Ready for initialization)",
                    details={"exists": False, "writable": True, "path": str(target)},
                )
            else:
                return HealthCheckResult(
                    name="database",
                    title="Database Storage",
                    status="fail",
                    message=f"{target} parent directory not writable",
                    details={"exists": False, "writable": False, "path": str(target)},
                )

        writable = os.access(target, os.W_OK)
        size_kb = target.stat().st_size / 1024

        try:
            conn = sqlite3.connect(str(target), check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("PRAGMA user_version")
            schema_version = cursor.fetchone()[0]
            cursor.execute("PRAGMA integrity_check")
            integrity = cursor.fetchone()[0]
            conn.close()
        except Exception as e:
            return HealthCheckResult(
                name="database",
                title="Database Storage",
                status="fail",
                message=f"Database corruption or connection failure: {e}",
                details={"exists": True, "writable": writable, "error": str(e), "path": str(target)},
            )

        if integrity != "ok":
            status = "fail"
            msg = f"Integrity check failed: {integrity}"
        elif schema_version < 2:
            status = "warn"
            msg = f"{target} (Schema v{schema_version} - Migration to v2 pending, {size_kb:.1f} KB)"
        else:
            status = "ok"
            msg = f"{target} (Schema v{schema_version}, {size_kb:.1f} KB, Integrity: OK)"

        return HealthCheckResult(
            name="database",
            title="Database Storage",
            status=status,
            message=msg,
            details={
                "path": str(target),
                "exists": True,
                "writable": writable,
                "schema_version": schema_version,
                "integrity": integrity,
                "size_kb": round(size_kb, 1),
            },
        )

    @classmethod
    def get_holding_pids(cls, lock_path: Path) -> List[int]:
        if not lock_path.exists():
            return []
        pids: List[int] = []
        try:
            res = subprocess.run(["fuser", str(lock_path)], capture_output=True, text=True)
            if res.stdout:
                for token in res.stdout.strip().split():
                    if token.isdigit():
                        pids.append(int(token))
        except Exception:
            pass
        return pids

    @classmethod
    def check_locks(cls) -> HealthCheckResult:
        lock_files = [
            Path("/var/lib/dpkg/lock-frontend"),
            Path("/var/lib/dpkg/lock"),
            Path("/var/lib/apt/lists/lock"),
            Path("/var/cache/apt/archives/lock"),
        ]

        active_holders: List[Dict[str, Any]] = []
        stale_locks: List[Dict[str, Any]] = []

        for lock in lock_files:
            if not lock.exists():
                continue
            pids = cls.get_holding_pids(lock)
            for pid in pids:
                try:
                    os.kill(pid, 0)
                    # Process is alive
                    comm = ""
                    try:
                        comm = Path(f"/proc/{pid}/comm").read_text().strip()
                    except Exception:
                        pass
                    active_holders.append({"file": str(lock), "pid": pid, "comm": comm})
                except OSError:
                    # Defunct / dead process
                    stale_locks.append({"file": str(lock), "pid": pid})

        if stale_locks:
            stale_descs = [f"{Path(s['file']).name} (PID {s['pid']})" for s in stale_locks]
            status = "fail"
            msg = f"Stale lock(s) detected with dead PID(s): {', '.join(stale_descs)}. Run 'ulum doctor --fix'!"
        elif active_holders:
            status = "warn"
            msg = f"Package manager lock actively held by {active_holders[0].get('comm') or 'process'} (PID {active_holders[0]['pid']})"
        else:
            status = "ok"
            msg = "No active or stale package manager locks detected"

        return HealthCheckResult(
            name="locks",
            title="Package Manager Locks",
            status=status,
            message=msg,
            details={
                "active_holders": active_holders,
                "stale_locks": stale_locks,
                "is_locked": bool(active_holders or stale_locks),
            },
        )

    @classmethod
    def check_scan_freshness(cls, db_path: Optional[Path] = None) -> HealthCheckResult:
        try:
            conn = init_db(db_path)
            repo = Repository(conn)
            last_scan_str = repo.get_setting("last_scan_at")
            last_check_str = repo.get_setting("last_check_at")
            conn.close()
        except Exception:
            last_scan_str = None
            last_check_str = None

        target_time_str = last_scan_str or last_check_str
        if not target_time_str:
            return HealthCheckResult(
                name="scan_freshness",
                title="Inventory & Scan Freshness",
                status="warn",
                message="No inventory scan recorded yet. Run 'ulum scan' to build initial inventory.",
                details={"last_scan_at": None, "age_hours": None},
            )

        try:
            target_dt = datetime.fromisoformat(target_time_str)
            if target_dt.tzinfo is None:
                target_dt = target_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_hours = (now - target_dt).total_seconds() / 3600.0

            if age_hours < 24.0:
                status = "ok"
                msg = f"Inventory scan completed {age_hours:.1f} hours ago"
            else:
                status = "warn"
                msg = f"Inventory scan is older than 24 hours ({age_hours:.1f} hours ago). Run 'ulum scan' to refresh."

            return HealthCheckResult(
                name="scan_freshness",
                title="Inventory & Scan Freshness",
                status=status,
                message=msg,
                details={
                    "last_scan_at": target_time_str,
                    "age_hours": round(age_hours, 1),
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name="scan_freshness",
                title="Inventory & Scan Freshness",
                status="warn",
                message=f"Could not parse last scan timestamp: {e}",
                details={"last_scan_at": target_time_str, "error": str(e)},
            )

    @classmethod
    def check_version_and_updates(cls, check_online: bool = True) -> HealthCheckResult:
        current_version = "0.4.0"
        latest_version = current_version
        update_available = False
        release_url = ""

        if check_online:
            try:
                rel = SelfUpdater.check_latest_release(current_version=current_version, timeout=2)
                latest_version = rel.get("latest_version") or current_version
                update_available = rel.get("update_available", False)
                release_url = rel.get("release_url", "")
            except Exception as e:
                logger.debug("Failed online update check: %s", e)

        if update_available:
            status = "warn"
            msg = f"v{current_version} installed; update available (v{latest_version}). Run 'ulum self-update'."
        else:
            status = "ok"
            msg = f"v{current_version} (Up to date)"

        return HealthCheckResult(
            name="version",
            title="ULUM Version & Updates",
            status=status,
            message=msg,
            details={
                "current_version": current_version,
                "latest_version": latest_version,
                "update_available": update_available,
                "release_url": release_url,
            },
        )

    @classmethod
    def run_all_checks(
        cls,
        db_path: Optional[Path] = None,
        check_online: bool = True,
        live_repo_check: bool = False,
    ) -> DoctorReport:
        """Executes all 8 diagnostic checks in strict order."""
        checks: List[HealthCheckResult] = [
            cls.check_distribution(),
            cls.check_package_managers(),
            cls.check_repositories(live_network=live_repo_check),
            cls.check_boot_health(),
            cls.check_database(db_path=db_path),
            cls.check_locks(),
            cls.check_scan_freshness(db_path=db_path),
            cls.check_version_and_updates(check_online=check_online),
        ]

        failing = [c.title for c in checks if c.status == "fail"]
        warning = [c.title for c in checks if c.status == "warn"]

        if failing:
            overall_status = "failed"
            exit_code = 1
        elif warning:
            overall_status = "degraded"
            exit_code = 0
        else:
            overall_status = "healthy"
            exit_code = 0

        now_iso = datetime.now(timezone.utc).isoformat()
        return DoctorReport(
            timestamp=now_iso,
            overall_status=overall_status,
            exit_code=exit_code,
            failing_checks=failing,
            checks=checks,
        )

    @classmethod
    def repair_stale_locks(cls) -> Dict[str, Any]:
        """Safely cleans stale locks where holding PID is dead and configures broken dpkg states."""
        lock_files = [
            Path("/var/lib/dpkg/lock-frontend"),
            Path("/var/lib/dpkg/lock"),
            Path("/var/lib/apt/lists/lock"),
            Path("/var/cache/apt/archives/lock"),
        ]

        removed_locks: List[str] = []
        for lock in lock_files:
            if not lock.exists():
                continue
            pids = cls.get_holding_pids(lock)
            if not pids:
                continue
            is_stale = True
            for pid in pids:
                try:
                    os.kill(pid, 0)
                    is_stale = False
                    break
                except OSError:
                    pass
            if is_stale and (is_root() or command_exists("sudo")):
                try:
                    run_cmd(["rm", "-f", str(lock)], require_root=True)
                    removed_locks.append(str(lock))
                except Exception as e:
                    logger.error("Failed to remove stale lock %s: %s", lock, e)

        # Interrupted dpkg state recovery
        dpkg_configured = False
        apt_fixed = False
        if command_exists("dpkg") and command_exists("apt-get"):
            try:
                run_cmd(["dpkg", "--configure", "-a"], require_root=True)
                dpkg_configured = True
            except Exception as e:
                logger.error("dpkg --configure -a failed: %s", e)

            try:
                run_cmd(["apt-get", "install", "-f", "-y"], require_root=True)
                apt_fixed = True
            except Exception as e:
                logger.error("apt-get install -f failed: %s", e)

        return {
            "removed_stale_locks": removed_locks,
            "dpkg_configured": dpkg_configured,
            "apt_fixed": apt_fixed,
            "success": dpkg_configured and apt_fixed,
        }
