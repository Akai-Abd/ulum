from ulum.core.models import ApplicationRecord, ScopeType, SourceType, UpdateRecord

def test_save_and_retrieve_applications(temp_db):
    repo, _ = temp_db
    app1 = ApplicationRecord(
        source=SourceType.APT,
        source_scope=ScopeType.SYSTEM,
        package_id="curl",
        display_name="curl",
        installed_version="7.88.1",
        install_location="/usr/bin/curl",
    )
    app2 = ApplicationRecord(
        source=SourceType.FLATPAK,
        source_scope=ScopeType.USER,
        package_id="org.mozilla.firefox",
        display_name="Firefox",
        installed_version="125.0",
    )
    repo.save_applications([app1, app2])

    apps = repo.get_applications()
    assert len(apps) == 2
    ids = {a.qualified_id for a in apps}
    assert "apt:curl" in ids
    assert "flatpak:org.mozilla.firefox" in ids

    # Test query by id
    retrieved = repo.get_application_by_id("apt:curl")
    assert retrieved is not None
    assert retrieved.display_name == "curl"

def test_updates_and_history(temp_db):
    repo, _ = temp_db
    app = ApplicationRecord(
        source=SourceType.APT,
        source_scope=ScopeType.SYSTEM,
        package_id="git",
        display_name="git",
        installed_version="2.43.0",
    )
    upd = UpdateRecord(application=app, available_version="2.43.2")
    repo.save_updates([upd])

    updates = repo.get_updates()
    assert len(updates) == 1
    assert updates[0]["package_id"] == "git"
    assert updates[0]["available_version"] == "2.43.2"

    repo.record_update_history(
        source="apt",
        package_id="git",
        previous_version="2.43.0",
        new_version="2.43.2",
        status="success",
        exit_code=0,
        started_at="2026-11-20T00:00:00Z",
        finished_at="2026-11-20T00:00:05Z",
    )
    history = repo.get_update_history()
    assert len(history) == 1
    assert history[0]["status"] == "success"

def test_removal_history(temp_db):
    repo, _ = temp_db
    repo.record_removal_history(
        source="snap",
        package_id="vlc",
        application_name="VLC",
        removal_mode="complete",
        removed_packages=["vlc"],
        removed_paths=["/home/user/snap/vlc"],
        preserved_paths=[],
        status="success",
        exit_code=0,
        started_at="2026-11-20T00:00:00Z",
        finished_at="2026-11-20T00:00:10Z",
    )
    hist = repo.get_removal_history()
    assert len(hist) == 1
    assert hist[0]["package_id"] == "vlc"
    assert "vlc" in hist[0]["removed_packages"]
