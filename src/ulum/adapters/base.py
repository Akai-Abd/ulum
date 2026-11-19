from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Sequence
from ulum.core.models import ApplicationRecord, ExecutionResult, RemovalPlan, UpdateRecord

class BaseAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the adapter (e.g. 'apt', 'flatpak', 'snap')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if native binaries for this adapter are installed."""
        pass

    @abstractmethod
    def list_installed(self) -> List[ApplicationRecord]:
        """Scan and return installed applications."""
        pass

    @abstractmethod
    def check_updates(self, refresh: bool = False) -> List[UpdateRecord]:
        """Query available updates."""
        pass

    @abstractmethod
    def build_update_command(self, targets: Optional[Sequence[str]] = None) -> List[str]:
        """Generate subprocess command list to execute update."""
        pass

    @abstractmethod
    def build_removal_plan(self, target: ApplicationRecord, complete: bool = False) -> RemovalPlan:
        """Analyze package and produce an immutable RemovalPlan."""
        pass

    @abstractmethod
    def execute_update(self, targets: Optional[Sequence[str]] = None) -> ExecutionResult:
        """Execute updates natively."""
        pass

    @abstractmethod
    def execute_native_removal(self, plan: RemovalPlan) -> ExecutionResult:
        """Execute native package manager removal."""
        pass

    @abstractmethod
    def get_dependencies(self, package_id: str) -> Dict[str, List[str]]:
        """Return dependency information for a package."""
        pass

    @abstractmethod
    def verify_state(self, package_id: str) -> bool:
        """Return True if package is still installed, False otherwise."""
        pass
