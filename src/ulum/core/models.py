from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

class SourceType(str, Enum):
    APT = "apt"
    FLATPAK = "flatpak"
    SNAP = "snap"

class ScopeType(str, Enum):
    SYSTEM = "system"
    USER = "user"

class ConfidenceLevel(str, Enum):
    VERIFIED = "verified"
    PROBABLE = "probable"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class ApplicationRecord:
    source: SourceType
    source_scope: ScopeType
    package_id: str
    display_name: str
    installed_version: str
    install_location: Optional[str] = None
    update_supported: bool = True
    remove_supported: bool = True

    @property
    def qualified_id(self) -> str:
        return f"{self.source.value}:{self.package_id}"

@dataclass(frozen=True)
class UpdateRecord:
    application: ApplicationRecord
    available_version: str
    details: Optional[str] = None

@dataclass
class CleanupCandidate:
    path: Path
    candidate_type: str  # 'config', 'cache', 'data', 'log'
    evidence: str
    confidence: ConfidenceLevel
    estimated_size_bytes: int = 0
    approved: bool = False

@dataclass
class RemovalPlan:
    application: ApplicationRecord
    complete: bool
    native_command: list[str]
    packages_to_remove: list[str]
    dependencies_to_remove: list[str]
    cleanup_items: list[CleanupCandidate]
    preserved_items: list[str]
    estimated_freed_bytes: int = 0
    is_safe: bool = True
    safety_warnings: list[str] = field(default_factory=list)

@dataclass
class ExecutionResult:
    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    removed_items: list[str] = field(default_factory=list)
    preserved_items: list[str] = field(default_factory=list)
    error_summary: Optional[str] = None

@dataclass
class SystemInfo:
    distro_id: str
    distro_name: str
    distro_version: str
    arch: str
    kernel: str
    is_supported: bool
