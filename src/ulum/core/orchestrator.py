import datetime
from typing import Dict, List, Optional, Tuple
from ulum.adapters.apt import AptAdapter
from ulum.adapters.base import BaseAdapter
from ulum.adapters.flatpak import FlatpakAdapter
from ulum.adapters.snap import SnapAdapter
from ulum.core.config import UlumConfig
from ulum.core.models import (
    ApplicationRecord,
    ExecutionResult,
    RemovalPlan,
    UpdateRecord,
)
from ulum.db.repository import Repository
from ulum.removal.executor import RemovalExecutor
from ulum.removal.planner import RemovalPlanner
from ulum.utils.logging import logger

class Orchestrator:
    def __init__(self, repo: Repository, config: UlumConfig):
        self.repo = repo
        self.config = config
        self.adapters: Dict[str, BaseAdapter] = {
            "apt": AptAdapter(),
            "flatpak": FlatpakAdapter(),
            "snap": SnapAdapter(),
        }

    def get_available_adapters(self) -> Dict[str, BaseAdapter]:
        return {
            name: adp
            for name, adp in self.adapters.items()
            if name in self.config.enabled_adapters and adp.is_available()
        }

    def scan_all(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for name, adapter in self.get_available_adapters().items():
            logger.info("Scanning installed packages for source '%s'...", name)
            apps = adapter.list_installed()
            self.repo.save_applications(apps)
            counts[name] = len(apps)
        return counts

    def check_updates(self, refresh: bool = False, source: Optional[str] = None) -> List[UpdateRecord]:
        all_updates: List[UpdateRecord] = []
        active_adapters = self.get_available_adapters()
        if source:
            active_adapters = {s: active_adapters[s]} if source in active_adapters else {}

        for name, adapter in active_adapters.items():
            logger.info("Checking updates for source '%s'...", name)
            try:
                upds = adapter.check_updates(refresh=refresh)
                # Filter out excluded packages
                filtered = [
                    u for u in upds
                    if u.application.qualified_id not in self.config.excluded_packages
                ]
                all_updates.extend(filtered)
            except Exception as e:
                logger.error("Failed checking updates for '%s': %s", name, e)

        self.repo.save_updates(all_updates, clear_previous=(source is None))
        return all_updates

    def execute_updates(
        self,
        targets: Optional[List[str]] = None,
        source: Optional[str] = None,
        dry_run: bool = False,
    ) -> List[Tuple[str, ExecutionResult]]:
        results: List[Tuple[str, ExecutionResult]] = []
        active_adapters = self.get_available_adapters()

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
