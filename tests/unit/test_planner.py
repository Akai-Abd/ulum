from pathlib import Path
from ulum.adapters.apt import AptAdapter
from ulum.core.models import ApplicationRecord, ScopeType, SourceType
from ulum.removal.planner import RemovalPlanner

def test_removal_planner_standard(monkeypatch):
    adapter = AptAdapter()
    target = ApplicationRecord(
        source=SourceType.APT,
        source_scope=ScopeType.SYSTEM,
        package_id="testpkg",
        display_name="testpkg",
        installed_version="1.0",
    )

    import ulum.adapters.apt as apt_module
    import subprocess
    monkeypatch.setattr(apt_module, "run_cmd", lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, "", ""))

    planner = RemovalPlanner(adapter)
    plan = planner.create_plan(target, complete=False)

    assert plan.application.package_id == "testpkg"
    assert "remove" in plan.native_command
    assert not plan.complete
    assert plan.is_safe

def test_removal_planner_complete_with_valid_candidate(monkeypatch, tmp_path):
    adapter = AptAdapter()
    target = ApplicationRecord(
        source=SourceType.APT,
        source_scope=ScopeType.SYSTEM,
        package_id="mytool",
        display_name="mytool",
        installed_version="1.0",
    )

    fake_home = tmp_path / "home"
    config_dir = fake_home / ".config" / "mytool"
    config_dir.mkdir(parents=True)
    dummy_file = config_dir / "settings.json"
    dummy_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: fake_home)
    import ulum.adapters.apt as apt_module
    import subprocess
    monkeypatch.setattr(apt_module, "run_cmd", lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, "", ""))

    planner = RemovalPlanner(adapter)
    plan = planner.create_plan(target, complete=True)

    assert plan.complete
    assert "purge" in plan.native_command
    assert len(plan.cleanup_items) == 1
    assert plan.cleanup_items[0].path == config_dir
    assert plan.estimated_freed_bytes > 0
