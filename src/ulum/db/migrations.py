import sqlite3
from ulum.utils.logging import logger

CURRENT_SCHEMA_VERSION = 2

def _get_user_version(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("PRAGMA user_version")
    row = cursor.fetchone()
    return int(row[0]) if row else 0

def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {version}")

def run_migrations(conn: sqlite3.Connection) -> None:
    """Run all pending schema migrations sequentially."""
    current_version = _get_user_version(conn)
    if current_version >= CURRENT_SCHEMA_VERSION:
        return

    with conn:
        if current_version < 1:
            # Baseline v0.3.0 schema
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS applications (
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

                CREATE TABLE IF NOT EXISTS updates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    package_id TEXT NOT NULL,
                    current_version TEXT NOT NULL,
                    available_version TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    details TEXT,
                    UNIQUE(source, package_id)
                );

                CREATE TABLE IF NOT EXISTS update_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    package_id TEXT NOT NULL,
                    previous_version TEXT,
                    new_version TEXT,
                    status TEXT NOT NULL,
                    exit_code INTEGER,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    error_summary TEXT
                );

                CREATE TABLE IF NOT EXISTS removal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    package_id TEXT NOT NULL,
                    application_name TEXT NOT NULL,
                    removal_mode TEXT NOT NULL,
                    removed_packages TEXT,
                    removed_paths TEXT,
                    preserved_paths TEXT,
                    status TEXT NOT NULL,
                    exit_code INTEGER,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    error_summary TEXT
                );

                CREATE TABLE IF NOT EXISTS cleanup_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    package_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    candidate_type TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    estimated_size INTEGER DEFAULT 0,
                    review_status TEXT DEFAULT 'pending',
                    detected_at TEXT NOT NULL,
                    UNIQUE(path)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            _set_user_version(conn, 1)
            current_version = 1

        if current_version < 2:
            # Migration to version 2 (v0.4.0)
            table_info = conn.execute("PRAGMA table_info(updates)").fetchall()
            columns = [row[1] if isinstance(row, (list, tuple)) else row["name"] for row in table_info]
            if "urgency" not in columns:
                conn.execute("ALTER TABLE updates ADD COLUMN urgency TEXT NOT NULL DEFAULT 'Unknown'")

            conn.executescript("""
                CREATE TABLE IF NOT EXISTS repo_fixes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    line_number INTEGER,
                    line_text TEXT,
                    error TEXT,
                    first_failed_at TEXT,
                    second_failed_at TEXT,
                    backup_path TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    restored_at TEXT
                );

                CREATE TABLE IF NOT EXISTS kernel_cleans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kernel_release TEXT NOT NULL,
                    package_ids TEXT,
                    is_booted INTEGER DEFAULT 0,
                    is_fallback INTEGER DEFAULT 0,
                    estimated_freed_bytes INTEGER DEFAULT 0,
                    actual_freed_bytes INTEGER DEFAULT 0,
                    snapshot_tool TEXT,
                    snapshot_id TEXT,
                    snapshot_taken INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    error_summary TEXT
                );

                CREATE TABLE IF NOT EXISTS appimage_integrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    binary_path TEXT NOT NULL,
                    desktop_path TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    backup_desktop_path TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_verified_at TEXT
                );

                CREATE TABLE IF NOT EXISTS download_estimates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id TEXT,
                    source TEXT NOT NULL,
                    estimated_bytes INTEGER DEFAULT 0,
                    estimated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS self_updates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_version TEXT NOT NULL,
                    to_version TEXT NOT NULL,
                    release_url TEXT,
                    download_sha256 TEXT,
                    verified INTEGER DEFAULT 0,
                    rollback_artefact_path TEXT,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    error_summary TEXT
                );

                CREATE TABLE IF NOT EXISTS operation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_type TEXT NOT NULL,
                    target_id TEXT,
                    source TEXT,
                    status TEXT NOT NULL,
                    exit_code INTEGER,
                    approved_plan_summary TEXT,
                    backup_path TEXT,
                    snapshot_id TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    error_summary TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_apps_source_pkg ON applications(source, package_id);
                CREATE INDEX IF NOT EXISTS idx_updates_urgency ON updates(urgency, detected_at);
                CREATE INDEX IF NOT EXISTS idx_op_history_type_started ON operation_history(operation_type, started_at);
            """)
            _set_user_version(conn, 2)
            logger.info("Database migrated to schema version 2 (v0.4.0)")
