import datetime
import json
import sqlite3
from typing import List, Optional
from ulum.core.models import (
    ApplicationRecord,
    CleanupCandidate,
    ConfidenceLevel,
    ScopeType,
    SourceType,
    UpdateRecord,
)

class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_applications(self, apps: List[ApplicationRecord]) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.conn:
            for app in apps:
                self.conn.execute(
                    """
                    INSERT INTO applications (
                        source, source_scope, package_id, display_name,
                        installed_version, install_location, update_supported,
                        remove_supported, last_scanned_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, source_scope, package_id) DO UPDATE SET
                        display_name = excluded.display_name,
                        installed_version = excluded.installed_version,
                        install_location = excluded.install_location,
                        last_scanned_at = excluded.last_scanned_at
                    """,
                    (
                        app.source.value,
                        app.source_scope.value,
                        app.package_id,
                        app.display_name,
                        app.installed_version,
                        app.install_location,
                        1 if app.update_supported else 0,
                        1 if app.remove_supported else 0,
                        now,
                    ),
                )

    def get_applications(self, source: Optional[str] = None) -> List[ApplicationRecord]:
        query = "SELECT source, source_scope, package_id, display_name, installed_version, install_location, update_supported, remove_supported FROM applications"
        params = []
        if source:
            query += " WHERE source = ?"
            params.append(source)
        query += " ORDER BY display_name COLLATE NOCASE ASC"

        cursor = self.conn.execute(query, params)
        records = []
        for row in cursor.fetchall():
            records.append(
                ApplicationRecord(
                    source=SourceType(row["source"]),
                    source_scope=ScopeType(row["source_scope"]),
                    package_id=row["package_id"],
                    display_name=row["display_name"],
                    installed_version=row["installed_version"],
                    install_location=row["install_location"],
                    update_supported=bool(row["update_supported"]),
                    remove_supported=bool(row["remove_supported"]),
                )
            )
        return records

    def get_application_by_id(self, identifier: str) -> Optional[ApplicationRecord]:
        if ":" in identifier:
            source, pkg_id = identifier.split(":", 1)
            cursor = self.conn.execute(
                "SELECT * FROM applications WHERE source = ? AND package_id = ? LIMIT 1",
                (source, pkg_id),
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM applications WHERE package_id = ? OR display_name = ? LIMIT 1",
                (identifier, identifier),
            )
        row = cursor.fetchone()
        if not row:
            return None
        return ApplicationRecord(
            source=SourceType(row["source"]),
            source_scope=ScopeType(row["source_scope"]),
            package_id=row["package_id"],
            display_name=row["display_name"],
            installed_version=row["installed_version"],
            install_location=row["install_location"],
            update_supported=bool(row["update_supported"]),
            remove_supported=bool(row["remove_supported"]),
        )

    def save_updates(self, updates: List[UpdateRecord], clear_previous: bool = True) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.conn:
            if clear_previous:
                self.conn.execute("DELETE FROM updates")
            for upd in updates:
                self.conn.execute(
                    """
                    INSERT INTO updates (
                        source, package_id, current_version, available_version, detected_at, details
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, package_id) DO UPDATE SET
                        current_version = excluded.current_version,
                        available_version = excluded.available_version,
                        detected_at = excluded.detected_at,
                        details = excluded.details
                    """,
                    (
                        upd.application.source.value,
                        upd.application.package_id,
                        upd.application.installed_version,
                        upd.available_version,
                        now,
                        upd.details,
                    ),
                )

    def get_updates(self, source: Optional[str] = None) -> List[dict]:
        query = """
            SELECT u.id, u.source, u.package_id, a.display_name, u.current_version, u.available_version, u.detected_at, u.details
            FROM updates u
            LEFT JOIN applications a ON u.source = a.source AND u.package_id = a.package_id
        """
        params = []
        if source:
            query += " WHERE u.source = ?"
            params.append(source)
        query += " ORDER BY u.source, u.package_id ASC"

        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def record_update_history(
        self,
        source: str,
        package_id: str,
        previous_version: Optional[str],
        new_version: Optional[str],
        status: str,
        exit_code: int,
        started_at: str,
        finished_at: str,
        error_summary: Optional[str] = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO update_history (
                    source, package_id, previous_version, new_version,
                    status, exit_code, started_at, finished_at, error_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    package_id,
                    previous_version,
                    new_version,
                    status,
                    exit_code,
                    started_at,
                    finished_at,
                    error_summary,
                ),
            )

    def record_removal_history(
        self,
        source: str,
        package_id: str,
        application_name: str,
        removal_mode: str,
        removed_packages: List[str],
        removed_paths: List[str],
        preserved_paths: List[str],
        status: str,
        exit_code: int,
        started_at: str,
        finished_at: str,
        error_summary: Optional[str] = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO removal_history (
                    source, package_id, application_name, removal_mode,
                    removed_packages, removed_paths, preserved_paths,
                    status, exit_code, started_at, finished_at, error_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    package_id,
                    application_name,
                    removal_mode,
                    json.dumps(removed_packages),
                    json.dumps(removed_paths),
                    json.dumps(preserved_paths),
                    status,
                    exit_code,
                    started_at,
                    finished_at,
                    error_summary,
                ),
            )

    def get_update_history(self, limit: int = 50) -> List[dict]:
        cursor = self.conn.execute(
            """
            SELECT id, source, package_id, previous_version, new_version, status, exit_code, started_at, finished_at, error_summary
            FROM update_history
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_removal_history(self, limit: int = 50) -> List[dict]:
        cursor = self.conn.execute(
            """
            SELECT id, source, package_id, application_name, removal_mode, removed_packages, removed_paths, preserved_paths, status, exit_code, started_at, finished_at, error_summary
            FROM removal_history
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        )
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d["removed_packages"] = json.loads(d["removed_packages"] or "[]")
            d["removed_paths"] = json.loads(d["removed_paths"] or "[]")
            d["preserved_paths"] = json.loads(d["preserved_paths"] or "[]")
            results.append(d)
        return results

    def save_cleanup_candidates(self, candidates: List[CleanupCandidate], source: str, package_id: str) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.conn:
            for c in candidates:
                self.conn.execute(
                    """
                    INSERT INTO cleanup_candidates (
                        source, package_id, path, candidate_type, evidence,
                        confidence, estimated_size, review_status, detected_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    ON CONFLICT(path) DO UPDATE SET
                        evidence = excluded.evidence,
                        confidence = excluded.confidence,
                        estimated_size = excluded.estimated_size,
                        detected_at = excluded.detected_at
                    """,
                    (
                        source,
                        package_id,
                        str(c.path),
                        c.candidate_type,
                        c.evidence,
                        c.confidence.value,
                        c.estimated_size_bytes,
                        now,
                    ),
                )

    def get_cleanup_candidates(self, confidence: Optional[str] = None) -> List[dict]:
        query = "SELECT * FROM cleanup_candidates WHERE review_status = 'pending'"
        params = []
        if confidence:
            query += " AND confidence = ?"
            params.append(confidence)
        query += " ORDER BY confidence, path ASC"
        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def mark_candidate_removed(self, path: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM cleanup_candidates WHERE path = ?", (path,))
