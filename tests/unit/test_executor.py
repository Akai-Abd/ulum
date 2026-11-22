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

def test_orchestrator_execute_security_only(temp_db, monkeypatch):
    from ulum.core.config import UlumConfig
    from ulum.core.orchestrator import Orchestrator
    from ulum.core.models import UpdateRecord

    repo, _ = temp_db
    config = UlumConfig()
    orc = Orchestrator(repo, config)

    sec_app = ApplicationRecord(SourceType.APT, ScopeType.SYSTEM, "curl", "curl", "1.0")
    feat_app = ApplicationRecord(SourceType.APT, ScopeType.SYSTEM, "vim", "vim", "2.0")
    repo.save_updates([
        UpdateRecord(sec_app, "1.1", urgency="Security"),
        UpdateRecord(feat_app, "2.1", urgency="Unknown"),
    ])
    assert len(repo.get_updates()) == 2

    executed_targets = []
    def mock_execute(targets=None):
        if targets:
            executed_targets.extend(targets)
        return ExecutionResult(success=True, exit_code=0)

    monkeypatch.setattr(orc.adapters["apt"], "execute_update", mock_execute)

    results = orc.execute_updates(security_only=True, dry_run=False)
    assert len(results) == 1
    assert results[0][1].success
    assert executed_targets == ["curl"]

    # Security update was cleared, feature update remains
    remaining = repo.get_updates()
    assert len(remaining) == 1
    assert remaining[0]["package_id"] == "vim"

    # Operation history entry recorded
    op_hist = repo.get_operation_history(operation_type="update")
    assert len(op_hist) >= 1
    assert op_hist[0]["status"] == "success"

def test_orchestrator_parallel_check_updates_and_timeout(temp_db, monkeypatch):
    import time
    from ulum.core.config import UlumConfig
    from ulum.core.orchestrator import Orchestrator
    from ulum.core.models import UpdateRecord

    repo, _ = temp_db
    config = UlumConfig(enabled_adapters=["apt", "flatpak"])
    orc = Orchestrator(repo, config)

    # Mock APT: fast with 1 update
    apt_app = ApplicationRecord(SourceType.APT, ScopeType.SYSTEM, "curl", "curl", "1.0")
    monkeypatch.setattr(orc.adapters["apt"], "is_available", lambda: True)
    monkeypatch.setattr(orc.adapters["apt"], "check_updates", lambda refresh=False: [UpdateRecord(apt_app, "1.1", urgency="Security")])

    # Mock Flatpak: hangs
    def slow_check(refresh=False):
        time.sleep(1.0)
        return []

    monkeypatch.setattr(orc.adapters["flatpak"], "is_available", lambda: True)
    monkeypatch.setattr(orc.adapters["flatpak"], "check_updates", slow_check)

    # Run check with a 0.2s timeout for testing
    detailed = orc.check_updates_detailed(refresh=True, timeout=0.2)
    assert len(detailed["updates"]) == 1
    assert detailed["updates"][0].application.package_id == "curl"
    assert detailed["source_status"]["apt"]["status"] == "success"
    assert detailed["source_status"]["flatpak"]["status"] == "failed"
    assert "Timed out" in detailed["source_status"]["flatpak"]["error"]

def test_orchestrator_check_updates_cached(temp_db, monkeypatch):
    from ulum.core.config import UlumConfig
    from ulum.core.orchestrator import Orchestrator
    from ulum.core.models import UpdateRecord

    repo, _ = temp_db
    config = UlumConfig(enabled_adapters=["apt"])
    orc = Orchestrator(repo, config)

    apt_app = ApplicationRecord(SourceType.APT, ScopeType.SYSTEM, "curl", "curl", "1.0")
    monkeypatch.setattr(orc.adapters["apt"], "is_available", lambda: True)
    monkeypatch.setattr(orc.adapters["apt"], "check_updates", lambda refresh=False: [UpdateRecord(apt_app, "1.1")])

    # First check: live
    res1 = orc.check_updates_detailed(refresh=False)
    assert not res1["is_cached"]

    # Second check without refresh: cached
    res2 = orc.check_updates_detailed(refresh=False)
    assert res2["is_cached"]
    assert len(res2["updates"]) == 1
    assert res2["updates"][0].application.package_id == "curl"

