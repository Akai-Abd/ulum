import os
import sqlite3
from pathlib import Path

def get_data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    data_dir = base / "ulum"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

def get_db_path() -> Path:
    override = os.environ.get("ULUM_DB_PATH")
    if override:
        path = Path(override)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return get_data_dir() / "ulum.db"

def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    target = db_path if db_path is not None else get_db_path()
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    with conn:
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
    return conn
