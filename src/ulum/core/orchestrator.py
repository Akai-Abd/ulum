import asyncio
import datetime
import time
from typing import Any, Dict, List, Optional, Tuple
from ulum.adapters.apt import AptAdapter
from ulum.adapters.appimage import AppImageAdapter
from ulum.adapters.base import BaseAdapter
from ulum.adapters.flatpak import FlatpakAdapter
from ulum.adapters.snap import SnapAdapter
from ulum.core.config import UlumConfig
from ulum.core.models import (
    ApplicationRecord,
    ExecutionResult,
    RemovalPlan,
    ScopeType,
    SourceType,
    UpdateRecord,
    is_security_only,
)
from ulum.db.repository import Repository
from ulum.removal.executor import RemovalExecutor
from ulum.removal.planner import RemovalPlanner
from ulum.utils.logging import logger

def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)

class Orchestrator:
    def __init__(self, repo: Repository, config: UlumConfig):
        self.repo = repo
        self.config = config
        self.adapters: Dict[str, BaseAdapter] = {
            "apt": AptAdapter(),
            "flatpak": FlatpakAdapter(),
            "snap": SnapAdapter(),
            "appimage": AppImageAdapter(),
        }

    def get_available_adapters(self) -> Dict[str, BaseAdapter]:
        return {
            name: adp
            for name, adp in self.adapters.items()
            if name in self.config.enabled_adapters and adp.is_available()
        }

    async def _scan_source_async(
        self, name: str, adapter: BaseAdapter, timeout: float
    ) -> Tuple[str, List[ApplicationRecord], float, Optional[str]]:
        start_time = time.perf_counter()
        try:
            apps = await asyncio.wait_for(
                asyncio.to_thread(adapter.list_installed),
                timeout=timeout,
            )
            elapsed = time.perf_counter() - start_time
            return (name, apps, elapsed, None)
        except asyncio.TimeoutError:
            elapsed = time.perf_counter() - start_time
            logger.error("Adapter '%s' timed out scanning after %.1fs", name, timeout)
            return (name, [], elapsed, f"Timed out after {int(timeout)}s")
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error("Failed scanning installed packages for '%s': %s", name, e)
            return (name, [], elapsed, str(e))

    async def _scan_all_parallel(self, active_adapters: Dict[str, BaseAdapter], timeout: float):
        tasks = [
            self._scan_source_async(name, adapter, timeout=timeout)
            for name, adapter in active_adapters.items()
        ]
        return await asyncio.gather(*tasks)

    def scan_all(self, timeout: float = 30.0) -> Dict[str, int]:
        active = self.get_available_adapters()
        results = _run_async(self._scan_all_parallel(active, timeout=timeout))
        counts: Dict[str, int] = {}
        for name, apps, elapsed, err in results:
            if err is None:
                self.repo.save_applications(apps, prune_source=name)
                counts[name] = len(apps)
            else:
                logger.error("Scan error for '%s': %s", name, err)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.repo.set_setting("last_scan_at", now_iso)
        return counts

    async def _check_source_async(
        self, name: str, adapter: BaseAdapter, refresh: bool, timeout: float
    ) -> Tuple[str, List[UpdateRecord], float, Optional[str]]:
        start_time = time.perf_counter()
        try:
            upds = await asyncio.wait_for(
                asyncio.to_thread(adapter.check_updates, refresh=refresh),
                timeout=timeout,
            )
            elapsed = time.perf_counter() - start_time
            filtered = [
                u for u in upds
                if u.application.qualified_id not in self.config.excluded_packages
            ]
            return (name, filtered, elapsed, None)
        except asyncio.TimeoutError:
            elapsed = time.perf_counter() - start_time
            logger.error("Adapter '%s' timed out checking updates after %.1fs", name, timeout)
            return (name, [], elapsed, f"Timed out after {int(timeout)}s")
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error("Failed checking updates for '%s': %s", name, e)
            return (name, [], elapsed, str(e))

    async def _check_all_parallel(
        self, active_adapters: Dict[str, BaseAdapter], refresh: bool, timeout: float
    ):
        tasks = [
            self._check_source_async(name, adapter, refresh=refresh, timeout=timeout)
            for name, adapter in active_adapters.items()
        ]
        return await asyncio.gather(*tasks)

    def check_updates_detailed(
        self,
        refresh: bool = False,
        source: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        active_adapters = self.get_available_adapters()
        if source:
            if source in self.adapters and self.adapters[source].is_available():
                active_adapters = {source: self.adapters[source]}
            else:
                active_adapters = {}

        # 1-hour cache check when not refreshing and inspecting all sources
        CACHE_TTL_SECONDS = 3600
        now = datetime.datetime.now(datetime.timezone.utc)
        last_check_str = self.repo.get_setting("last_check_at")

        if not refresh and not source and last_check_str:
            try:
                last_dt = datetime.datetime.fromisoformat(last_check_str)
                age = (now - last_dt).total_seconds()
                if age < CACHE_TTL_SECONDS:
                    cached_data = self.repo.get_updates()
                    cached_updates: List[UpdateRecord] = []
                    app_map = {a.package_id: a for a in self.repo.get_applications()}
                    for row in cached_data:
                        src_enum = SourceType(row["source"]) if row["source"] in [s.value for s in SourceType] else SourceType.APT
                        app = app_map.get(row["package_id"]) or ApplicationRecord(
                            source=src_enum,
                            source_scope=ScopeType.SYSTEM,
                            package_id=row["package_id"],
                            display_name=row.get("display_name") or row["package_id"],
                            installed_version=row["current_version"],
                        )
                        cached_updates.append(
                            UpdateRecord(
                                application=app,
                                available_version=row["available_version"],
                                details=row.get("details"),
                                urgency=row.get("urgency", "Unknown"),
                            )
                        )
                    return {
                        "updates": cached_updates,
                        "source_status": {},
                        "is_cached": True,
                        "cache_age_seconds": age,
                    }
            except Exception as e:
                logger.debug("Failed reading cached updates: %s", e)

        # Run concurrent parallel checks across all active adapters
        results = _run_async(self._check_all_parallel(active_adapters, refresh=refresh, timeout=timeout))

        all_updates: List[UpdateRecord] = []
        source_status: Dict[str, dict] = {}
        for name, upds, elapsed, err in results:
            if err is None:
                all_updates.extend(upds)
                source_status[name] = {
                    "status": "success",
                    "elapsed": elapsed,
                    "count": len(upds),
                    "error": None,
                }
            else:
                source_status[name] = {
                    "status": "failed",
                    "elapsed": elapsed,
                    "count": 0,
                    "error": err,
                }

        self.repo.save_updates(all_updates, clear_previous=(source is None))
        self.repo.set_setting("last_check_at", now.isoformat())

        return {
            "updates": all_updates,
            "source_status": source_status,
            "is_cached": False,
            "cache_age_seconds": 0.0,
        }

    def check_updates(
        self, refresh: bool = False, source: Optional[str] = None, timeout: float = 30.0
    ) -> List[UpdateRecord]:
        return self.check_updates_detailed(refresh=refresh, source=source, timeout=timeout)["updates"]

    def get_update_download_summary(self) -> Dict[str, Any]:
        """Calculates total estimated download size and flags metered connection cautions."""
        from ulum.cli.display import format_bytes
        total_bytes = 0
        breakdown: Dict[str, Dict[str, Any]] = {}
        for name, adapter in self.get_available_adapters().items():
            if hasattr(adapter, "get_download_size"):
                try:
                    sz = adapter.get_download_size()
                except Exception:
                    sz = 0
                total_bytes += sz
                breakdown[name] = {"bytes": sz, "formatted": format_bytes(sz)}
            else:
                breakdown[name] = {"bytes": 0, "formatted": "0 B"}

        is_large = total_bytes > (1024 * 1024 * 1024)  # > 1 GB
        warning_msg = (
            f"Notice: Large download ({format_bytes(total_bytes)}) detected. Metered connection caution."
            if is_large else None
        )
        return {
            "total_bytes": total_bytes,
            "formatted_size": format_bytes(total_bytes),
            "is_large_download": is_large,
            "warning": warning_msg,
            "breakdown": breakdown,
        }

    def execute_updates(
        self,
        targets: Optional[List[str]] = None,
        source: Optional[str] = None,
        security_only: bool = False,
        dry_run: bool = False,
    ) -> List[Tuple[str, ExecutionResult]]:
        results: List[Tuple[str, ExecutionResult]] = []
        active_adapters = self.get_available_adapters()

        if security_only:
            pending_upds = self.repo.get_updates(source=source)
            sec_targets = [
                f"{u['source']}:{u['package_id']}"
                for u in pending_upds
                if is_security_only(u.get("urgency", "Unknown"))
            ]
            if not sec_targets:
                logger.info("No security updates found.")
                return []
            targets = sec_targets if not targets else [t for t in targets if t in sec_targets]

        if targets:
            # Group target package IDs by source
            grouped: Dict[str, List[str]] = {}
            for t in targets:
                if ":" in t:
                    src, pkg = t.split(":", 1)
                else:
                    app = self.repo.get_application_by_id(t)
                    src, pkg = (app.source.value, app.package_id) if app else ("apt", t)
                grouped.setdefault(src, []).append(pkg)

            for src, pkgs in grouped.items():
                if src in active_adapters:
                    adapter = active_adapters[src]
                    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    if dry_run:
                        cmd = adapter.build_update_command(pkgs)
                        res = ExecutionResult(success=True, exit_code=0, stdout=f"Dry-run command: {' '.join(cmd)}")
                    else:
                        res = adapter.execute_update(pkgs)
                    finished = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    if res.success and not dry_run:
                        for pkg in pkgs:
                            self.repo.delete_update(src, pkg)
                    for pkg in pkgs:
                        self.repo.record_update_history(
                            source=src,
                            package_id=pkg,
                            previous_version=None,
                            new_version=None,
                            status="success" if res.success else "failed",
                            exit_code=res.exit_code,
                            started_at=started,
                            finished_at=finished,
                            error_summary=res.error_summary,
                        )
                        self.repo.record_operation_history(
                            operation_type="update",
                            target_id=f"{src}:{pkg}",
                            source=src,
                            status="success" if res.success else "failed",
                            exit_code=res.exit_code,
                            approved_plan_summary=f"Update {src}:{pkg}",
                            started_at=started,
                            finished_at=finished,
                            error_summary=res.error_summary,
                        )
                    results.append((src, res))
        else:
            sources_to_run = [source] if source else list(active_adapters.keys())
            for src in sources_to_run:
                if src in active_adapters:
                    adapter = active_adapters[src]
                    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    if dry_run:
                        cmd = adapter.build_update_command()
                        res = ExecutionResult(success=True, exit_code=0, stdout=f"Dry-run command: {' '.join(cmd)}")
                    else:
                        res = adapter.execute_update()
                    finished = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    if res.success and not dry_run:
                        self.repo.delete_updates_by_source(src)
                    self.repo.record_update_history(
                        source=src,
                        package_id="<bulk>",
                        previous_version=None,
                        new_version=None,
                        status="success" if res.success else "failed",
                        exit_code=res.exit_code,
                        started_at=started,
                        finished_at=finished,
                        error_summary=res.error_summary,
                    )
                    self.repo.record_operation_history(
                        operation_type="update",
                        target_id=f"{src}:<bulk>",
                        source=src,
                        status="success" if res.success else "failed",
                        exit_code=res.exit_code,
                        approved_plan_summary=f"Bulk update {src}",
                        started_at=started,
                        finished_at=finished,
                        error_summary=res.error_summary,
                    )
                    results.append((src, res))

        return results

    def plan_removal(self, identifier: str, complete: bool = False) -> Tuple[ApplicationRecord, RemovalPlan]:
        app = self.repo.get_application_by_id(identifier)
        if not app:
            # Fallback: create ad-hoc record from identifier
            if ":" in identifier:
                src, pkg = identifier.split(":", 1)
            else:
                src, pkg = "apt", identifier
            from ulum.core.models import ScopeType, SourceType
            app = ApplicationRecord(
                source=SourceType(src),
                source_scope=ScopeType.SYSTEM,
                package_id=pkg,
                display_name=pkg,
                installed_version="unknown",
            )

        adapter = self.adapters.get(app.source.value)
        if not adapter:
            raise ValueError(f"No adapter found for source '{app.source.value}'")

        planner = RemovalPlanner(adapter)
        plan = planner.create_plan(app, complete=complete)
        return app, plan

    def execute_removal(self, plan: RemovalPlan, dry_run: bool = False) -> ExecutionResult:
        adapter = self.adapters.get(plan.application.source.value)
        if not adapter:
            raise ValueError(f"No adapter found for source '{plan.application.source.value}'")

        executor = RemovalExecutor(adapter)
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        res = executor.execute(plan, dry_run=dry_run, clean_files=plan.complete)
        finished = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if not dry_run:
            if res.success:
                self.repo.delete_application(plan.application.source.value, plan.application.package_id)
            self.repo.record_removal_history(
                source=plan.application.source.value,
                package_id=plan.application.package_id,
                application_name=plan.application.display_name,
                removal_mode="complete" if plan.complete else "standard",
                removed_packages=plan.packages_to_remove,
                removed_paths=res.removed_items,
                preserved_paths=res.preserved_items,
                status="success" if res.success else "failed",
                exit_code=res.exit_code,
                started_at=started,
                finished_at=finished,
                error_summary=res.error_summary,
            )
        return res
