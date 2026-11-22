import os
import sqlite3
from pathlib import Path

def get_data_dir() -> Path:
    pkexec_uid = os.environ.get("PKEXEC_UID")
    real_user = os.environ.get("SUDO_USER")
    if pkexec_uid:
        try:
            import pwd
            base = Path(pwd.getpwuid(int(pkexec_uid)).pw_dir) / ".local" / "share"
        except Exception:
            base = Path.home() / ".local" / "share"
    elif real_user:
        try:
            import pwd
            base = Path(pwd.getpwnam(real_user).pw_dir) / ".local" / "share"
        except Exception:
            base = Path.home() / ".local" / "share"
    else:
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
    from ulum.db.migrations import run_migrations

    target = db_path if db_path is not None else get_db_path()
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    run_migrations(conn)
    return conn
