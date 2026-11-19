import shutil
from pathlib import Path
from typing import List
from ulum.adapters.base import BaseAdapter
from ulum.core.models import ExecutionResult, RemovalPlan
from ulum.removal.safety import SafetyValidator
from ulum.utils.logging import logger

class RemovalExecutor:
    def __init__(self, adapter: BaseAdapter):
        self.adapter = adapter

    def execute(self, plan: RemovalPlan, dry_run: bool = False, clean_files: bool = True) -> ExecutionResult:
        if dry_run:
            logger.info("Dry-run: Simulated removal of %s", plan.application.qualified_id)
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout="Dry-run simulation completed. No changes made to system.",
                removed_items=[],
                preserved_items=[str(c.path) for c in plan.cleanup_items],
            )

        # 1. Native package manager uninstallation
        logger.info("Executing native removal: %s", " ".join(plan.native_command))
        native_res = self.adapter.execute_native_removal(plan)
        if not native_res.success:
            logger.error("Native removal failed with exit code %d: %s", native_res.exit_code, native_res.stderr)
            return native_res

        removed_items: List[str] = list(native_res.removed_items)
        preserved_items: List[str] = []

        # 2. Cleanup verified file candidates (only on success and if requested)
        if clean_files and plan.cleanup_items:
            for item in plan.cleanup_items:
                is_valid, reason = SafetyValidator.validate_cleanup_path(item.path)
                if not is_valid:
                    logger.warning("Re-validation rejected path '%s': %s", item.path, reason)
                    preserved_items.append(str(item.path))
                    continue

                if not item.path.exists():
                    continue

                try:
                    if item.path.is_dir() and not item.path.is_symlink():
                        shutil.rmtree(item.path)
                    else:
                        item.path.unlink()
                    removed_items.append(str(item.path))
                    logger.info("Cleaned up residual path: %s", item.path)
                except Exception as e:
                    logger.error("Failed removing '%s': %s", item.path, e)
                    preserved_items.append(str(item.path))

        return ExecutionResult(
            success=True,
            exit_code=0,
            stdout=native_res.stdout,
            stderr=native_res.stderr,
            removed_items=removed_items,
            preserved_items=preserved_items,
        )
