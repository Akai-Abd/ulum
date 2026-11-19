from pathlib import Path
from ulum.adapters.apt import AptAdapter
from ulum.core.models import (
    ApplicationRecord,
    CleanupCandidate,
    ConfidenceLevel,
    ExecutionResult,
    RemovalPlan,
    ScopeType,
    SourceType,
)
from ulum.removal.executor import RemovalExecutor

def test_removal_executor_dry_run(monkeypatch):
    adapter = AptAdapter()
    target = ApplicationRecord(
        source=SourceType.APT,
        source_scope=ScopeType.SYSTEM,
        package_id="curl",
        display_name="curl",
        installed_version="1.0",
    )
    plan = RemovalPlan(
        application=target,
        complete=False,
        native_command=["apt-get", "remove", "-y", "curl"],
        packages_to_remove=["curl"],
        dependencies_to_remove=[],
        cleanup_items=[],
        preserved_items=[],
    )

    executor = RemovalExecutor(adapter)
    res = executor.execute(plan, dry_run=True)
    assert res.success
    assert "Dry-run" in res.stdout

def test_removal_executor_real_execution(tmp_path, monkeypatch):
    adapter = AptAdapter()
    fake_home = tmp_path / "home"
    target_config = fake_home / ".config" / "testtool"
    target_config.mkdir(parents=True)
    (target_config / "config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(
        adapter,
        "execute_native_removal",
        lambda plan: ExecutionResult(success=True, exit_code=0, removed_items=["testtool"]),
    )

    target = ApplicationRecord(
        source=SourceType.APT,
        source_scope=ScopeType.SYSTEM,
        package_id="testtool",
        display_name="testtool",
        installed_version="1.0",
    )
    plan = RemovalPlan(
        application=target,
        complete=True,
        native_command=["apt-get", "purge", "-y", "testtool"],
        packages_to_remove=["testtool"],
        dependencies_to_remove=[],
        cleanup_items=[
            CleanupCandidate(
                path=target_config,
                candidate_type="config",
                evidence="Exact match",
                confidence=ConfidenceLevel.VERIFIED,
            )
        ],
        preserved_items=[],
    )

    executor = RemovalExecutor(adapter)
    res = executor.execute(plan, dry_run=False, clean_files=True)
    assert res.success
    assert str(target_config) in res.removed_items
    assert not target_config.exists()

def test_orchestrator_snapshot_failure_aborts(temp_db, monkeypatch):
    from ulum.core.config import UlumConfig
    from ulum.core.orchestrator import Orchestrator
    repo, _ = temp_db
    config = UlumConfig()
    orc = Orchestrator(repo, config)

    import ulum.core.system as system_module
    monkeypatch.setattr(system_module, "create_system_snapshot", lambda comment: (False, "Disk full"))

    results = orc.execute_updates(targets=["apt:curl"], create_snapshot=True, dry_run=False)
    assert len(results) == 1
    assert results[0][0] == "system"
    assert not results[0][1].success
    assert "Pre-update snapshot failed: Disk full" in results[0][1].stderr

def test_orchestrator_update_clears_pending_updates(temp_db, monkeypatch):
    from ulum.core.config import UlumConfig
    from ulum.core.orchestrator import Orchestrator
    from ulum.core.models import UpdateRecord
    repo, _ = temp_db
    config = UlumConfig()
    orc = Orchestrator(repo, config)

    app = ApplicationRecord(SourceType.APT, ScopeType.SYSTEM, "curl", "curl", "1.0")
    repo.save_updates([UpdateRecord(app, "1.1")])
    assert len(repo.get_updates()) == 1

    monkeypatch.setattr(
        orc.adapters["apt"],
        "execute_update",
        lambda targets=None: ExecutionResult(success=True, exit_code=0),
    )

    results = orc.execute_updates(targets=["apt:curl"], dry_run=False)
    assert results[0][1].success
    assert len(repo.get_updates()) == 0
