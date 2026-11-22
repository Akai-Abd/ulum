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

def test_delete_application_and_prune(temp_db):
    repo, _ = temp_db
    app1 = ApplicationRecord(SourceType.APT, ScopeType.SYSTEM, "curl", "curl", "7.88.1")
    app2 = ApplicationRecord(SourceType.APT, ScopeType.SYSTEM, "vim", "vim", "9.0")
    repo.save_applications([app1, app2])
    repo.save_updates([UpdateRecord(app1, "7.88.2")])

    # Delete curl
    repo.delete_application("apt", "curl")
    assert repo.get_application_by_id("apt:curl") is None
    assert len(repo.get_updates()) == 0
    assert repo.get_application_by_id("apt:vim") is not None

    # Prune apt source with only vim
    repo.save_applications([app1], prune_source="apt")
    assert repo.get_application_by_id("apt:curl") is not None
    assert repo.get_application_by_id("apt:vim") is None

def test_delete_updates(temp_db):
    repo, _ = temp_db
    app1 = ApplicationRecord(SourceType.APT, ScopeType.SYSTEM, "curl", "curl", "7.88.1")
    app2 = ApplicationRecord(SourceType.FLATPAK, ScopeType.USER, "org.app", "app", "1.0")
    repo.save_updates([UpdateRecord(app1, "7.88.2"), UpdateRecord(app2, "1.1")])
    assert len(repo.get_updates()) == 2

    repo.delete_update("apt", "curl")
    upds = repo.get_updates()
    assert len(upds) == 1
    assert upds[0]["package_id"] == "org.app"

    repo.delete_updates_by_source("flatpak")
    assert len(repo.get_updates()) == 0

def test_updates_urgency_field(temp_db):
    repo, _ = temp_db
    app = ApplicationRecord(SourceType.APT, ScopeType.SYSTEM, "curl", "curl", "7.88.1")
    upd = UpdateRecord(application=app, available_version="7.88.2", urgency="Security")
    repo.save_updates([upd])

    updates = repo.get_updates()
    assert len(updates) == 1
    assert updates[0]["urgency"] == "Security"

def test_operation_history_and_v2_tables(temp_db):
    repo, _ = temp_db

    # Test operation history
    op_id = repo.record_operation_history(
        operation_type="update",
        target_id="apt:curl",
        source="apt",
        status="success",
        exit_code=0,
        approved_plan_summary="Update curl 7.88.1 -> 7.88.2",
    )
    assert op_id > 0
    history = repo.get_operation_history(operation_type="update")
    assert len(history) == 1
    assert history[0]["target_id"] == "apt:curl"
    assert history[0]["status"] == "success"

    # Test repo_fixes
    fix_id = repo.record_repo_fix(
        file_path="/etc/apt/sources.list.d/broken.list",
        line_number=1,
        line_text="deb http://example.com/ubuntu noble main",
        error="404 Not Found",
        backup_path="/etc/apt/sources.list.d/broken.list.ulum-backup",
    )
    assert fix_id > 0
    fixes = repo.get_repo_fixes()
    assert len(fixes) == 1
    assert fixes[0]["status"] == "disabled"
    repo.mark_repo_fix_restored(fix_id)
    assert repo.get_repo_fixes(status="restored")[0]["id"] == fix_id

    # Test kernel_cleans
    kc_id = repo.record_kernel_clean(
        kernel_release="6.8.0-140-generic",
        package_ids=["linux-image-6.8.0-140-generic"],
        estimated_freed_bytes=100000000,
        actual_freed_bytes=100000000,
    )
    assert kc_id > 0

    # Test appimage_integrations
    ai_id = repo.record_appimage_integration(
        binary_path="/home/user/app.AppImage",
        desktop_path="/home/user/.local/share/applications/app.desktop",
        display_name="Test App",
    )
    assert ai_id > 0

    # Test self_updates
    su_id = repo.record_self_update(
        from_version="0.3.0",
        to_version="0.4.0",
        download_sha256="abcdef123456",
        verified=True,
    )
    assert su_id > 0

def test_migration_v1_to_v2(tmp_path):
    import sqlite3
    from ulum.db.migrations import run_migrations

    db_path = tmp_path / "test_legacy_v1.db"
    conn = sqlite3.connect(str(db_path))

    # Manually create v1 schema without urgency and without v2 tables
    conn.executescript("""
        CREATE TABLE applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_scope TEXT NOT NULL,
            package_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            installed_version TEXT NOT NULL,
            install_location TEXT,
            update_supported INTEGER NOT NULL DEFAULT 1,
            remove_supported INTEGER NOT NULL DEFAULT 1,
            last_scanned_at TEXT NOT NULL,
            UNIQUE(source, source_scope, package_id)
        );
        CREATE TABLE updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            package_id TEXT NOT NULL,
            current_version TEXT NOT NULL,
            available_version TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            details TEXT,
            UNIQUE(source, package_id)
        );
        PRAGMA user_version = 1;
    """)

    # Verify user_version is 1 and urgency column doesn't exist
    cols = [r[1] for r in conn.execute("PRAGMA table_info(updates)").fetchall()]
    assert "urgency" not in cols

    # Run migrations
    run_migrations(conn)

    # Verify user_version is 2
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    assert v == 2

    # Verify urgency column was added
    cols_after = [r[1] for r in conn.execute("PRAGMA table_info(updates)").fetchall()]
    assert "urgency" in cols_after

    # Verify new tables exist
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "operation_history" in tables
    assert "repo_fixes" in tables
    assert "kernel_cleans" in tables
    assert "appimage_integrations" in tables
    assert "download_estimates" in tables
    assert "self_updates" in tables

    conn.close()

