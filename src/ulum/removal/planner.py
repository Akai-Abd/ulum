from pathlib import Path
from typing import List
from ulum.adapters.base import BaseAdapter
from ulum.core.models import ApplicationRecord, CleanupCandidate, RemovalPlan
from ulum.removal.safety import SafetyValidator

def get_dir_size(path: Path) -> int:
    total = 0
    try:
        if path.is_file():
            return path.stat().st_size
        for entry in path.rglob("*"):
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
    except Exception:
        pass
    return total

class RemovalPlanner:
    def __init__(self, adapter: BaseAdapter):
        self.adapter = adapter

    def create_plan(self, target: ApplicationRecord, complete: bool = False) -> RemovalPlan:
        raw_plan = self.adapter.build_removal_plan(target, complete=complete)
        verified_items: List[CleanupCandidate] = []
        warnings = list(raw_plan.safety_warnings)
        total_bytes = 0

        for item in raw_plan.cleanup_items:
            is_valid, reason = SafetyValidator.validate_cleanup_path(item.path)
            if not is_valid:
                warnings.append(f"Excluded '{item.path}': {reason}")
                continue

            item.estimated_size_bytes = get_dir_size(item.path)
            total_bytes += item.estimated_size_bytes
            verified_items.append(item)

        is_safe = raw_plan.is_safe and not any("critical" in w.lower() for w in warnings)

        return RemovalPlan(
            application=target,
            complete=complete,
            native_command=raw_plan.native_command,
            packages_to_remove=raw_plan.packages_to_remove,
            dependencies_to_remove=raw_plan.dependencies_to_remove,
            cleanup_items=verified_items,
            preserved_items=raw_plan.preserved_items,
            estimated_freed_bytes=total_bytes,
            is_safe=is_safe,
            safety_warnings=warnings,
        )
