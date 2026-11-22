import datetime
import json
import sqlite3
import threading
from typing import List, Optional
from ulum.core.models import (
    ApplicationRecord,
    CleanupCandidate,
    ScopeType,
    SourceType,
    UpdateRecord,
)

class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._lock = threading.RLock()

    def save_applications(self, apps: List[ApplicationRecord], prune_source: Optional[str] = None) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            with self.conn:
                if apps:
                    rows = [
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
                        )
                        for app in apps
                    ]
                    self.conn.executemany(
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
                        rows,
                    )
                if prune_source:
                    self.conn.execute(
                        "DELETE FROM applications WHERE source = ? AND last_scanned_at < ?",
                        (prune_source, now),
                    )

    def delete_application(self, source: str, package_id: str) -> None:
        with self._lock:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM applications WHERE source = ? AND package_id = ?",
                    (source, package_id),
                )
                self.conn.execute(
                    "DELETE FROM updates WHERE source = ? AND package_id = ?",
                    (source, package_id),
                )

    def get_applications(self, source: Optional[str] = None) -> List[ApplicationRecord]:
        query = "SELECT source, source_scope, package_id, display_name, installed_version, install_location, update_supported, remove_supported FROM applications"
        params = []
        if source:
            query += " WHERE source = ?"
            params.append(source)
        query += " ORDER BY display_name COLLATE NOCASE ASC"

        with self._lock:
            cursor = self.conn.execute(query, params)
            rows = cursor.fetchall()

        records = []
        for row in rows:
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
        with self._lock:
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
        with self._lock:
            with self.conn:
                if clear_previous:
                    self.conn.execute("DELETE FROM updates")
                if updates:
                    rows = [
                        (
                            upd.application.source.value,
                            upd.application.package_id,
                            upd.application.installed_version,
                            upd.available_version,
                            now,
                            upd.details,
                            getattr(upd, "urgency", "Unknown") or "Unknown",
                        )
                        for upd in updates
                    ]
                    self.conn.executemany(
                        """
                        INSERT INTO updates (
                            source, package_id, current_version, available_version, detected_at, details, urgency
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source, package_id) DO UPDATE SET
                            current_version = excluded.current_version,
                            available_version = excluded.available_version,
                            detected_at = excluded.detected_at,
                            details = excluded.details,
                            urgency = excluded.urgency
                        """,
                        rows,
                    )

    def get_updates(self, source: Optional[str] = None) -> List[dict]:
        query = """
            SELECT u.id, u.source, u.package_id, a.display_name, u.current_version, u.available_version, u.detected_at, u.details, u.urgency
            FROM updates u
            LEFT JOIN applications a ON u.source = a.source AND u.package_id = a.package_id
        """
        params = []
        if source:
            query += " WHERE u.source = ?"
            params.append(source)
        query += " ORDER BY u.source, u.package_id ASC"

        with self._lock:
            cursor = self.conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def delete_update(self, source: str, package_id: str) -> None:
        with self._lock:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM updates WHERE source = ? AND package_id = ?",
                    (source, package_id),
                )

    def delete_updates_by_source(self, source: str) -> None:
        with self._lock:
            with self.conn:
                self.conn.execute("DELETE FROM updates WHERE source = ?", (source,))

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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            cursor = self.conn.execute(
                """
                SELECT id, source, package_id, application_name, removal_mode, removed_packages, removed_paths, preserved_paths, status, exit_code, started_at, finished_at, error_summary
                FROM removal_history
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        results = []
        for row in rows:
            d = dict(row)
            d["removed_packages"] = json.loads(d["removed_packages"] or "[]")
            d["removed_paths"] = json.loads(d["removed_paths"] or "[]")
            d["preserved_paths"] = json.loads(d["preserved_paths"] or "[]")
            results.append(d)
        return results

    def save_cleanup_candidates(self, candidates: List[CleanupCandidate], source: str, package_id: str) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            with self.conn:
                if candidates:
                    rows = [
                        (
                            source,
                            package_id,
                            str(c.path),
                            c.candidate_type,
                            c.evidence,
                            c.confidence.value,
                            c.estimated_size_bytes,
                            now,
                        )
                        for c in candidates
                    ]
                    self.conn.executemany(
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
                        rows,
                    )

    def get_cleanup_candidates(self, confidence: Optional[str] = None) -> List[dict]:
        query = "SELECT * FROM cleanup_candidates WHERE review_status = 'pending'"
        params = []
        if confidence:
            query += " AND confidence = ?"
            params.append(confidence)
        query += " ORDER BY confidence, path ASC"
        with self._lock:
            cursor = self.conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def mark_candidate_removed(self, path: str) -> None:
        with self._lock:
            with self.conn:
                self.conn.execute("DELETE FROM cleanup_candidates WHERE path = ?", (path,))

    def record_operation_history(
        self,
        operation_type: str,
        target_id: Optional[str] = None,
        source: Optional[str] = None,
        status: str = "success",
        exit_code: int = 0,
        approved_plan_summary: Optional[str] = None,
        backup_path: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        error_summary: Optional[str] = None,
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        start = started_at or now
        finish = finished_at or now
        with self._lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO operation_history (
                        operation_type, target_id, source, status, exit_code,
                        approved_plan_summary, backup_path, snapshot_id,
                        started_at, finished_at, error_summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        operation_type,
                        target_id,
                        source,
                        status,
                        exit_code,
                        approved_plan_summary,
                        backup_path,
                        snapshot_id,
                        start,
                        finish,
                        error_summary,
                    ),
                )
                return cursor.lastrowid or 0

    def get_operation_history(
        self, limit: int = 50, operation_type: Optional[str] = None
    ) -> List[dict]:
        query = "SELECT * FROM operation_history"
        params: list = []
        if operation_type:
            query += " WHERE operation_type = ?"
            params.append(operation_type)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            cursor = self.conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def record_repo_fix(
        self,
        file_path: str,
        line_number: Optional[int],
        line_text: Optional[str],
        error: Optional[str],
        first_failed_at: Optional[str] = None,
        second_failed_at: Optional[str] = None,
        backup_path: Optional[str] = None,
        status: str = "disabled",
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO repo_fixes (
                        file_path, line_number, line_text, error,
                        first_failed_at, second_failed_at, backup_path, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_path,
                        line_number,
                        line_text,
                        error,
                        first_failed_at or now,
                        second_failed_at,
                        backup_path,
                        status,
                        now,
                    ),
                )
                return cursor.lastrowid or 0

    def get_repo_fixes(self, status: Optional[str] = None) -> List[dict]:
        query = "SELECT * FROM repo_fixes"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY id DESC"
        with self._lock:
            cursor = self.conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def mark_repo_fix_restored(self, fix_id: int) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            with self.conn:
                self.conn.execute(
                    "UPDATE repo_fixes SET status = 'restored', restored_at = ? WHERE id = ?",
                    (now, fix_id),
                )

    def record_kernel_clean(
        self,
        kernel_release: str,
        package_ids: List[str],
        is_booted: bool = False,
        is_fallback: bool = False,
        estimated_freed_bytes: int = 0,
        actual_freed_bytes: int = 0,
        snapshot_tool: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        snapshot_taken: bool = False,
        status: str = "success",
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        error_summary: Optional[str] = None,
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO kernel_cleans (
                        kernel_release, package_ids, is_booted, is_fallback,
                        estimated_freed_bytes, actual_freed_bytes, snapshot_tool,
                        snapshot_id, snapshot_taken, status, started_at, finished_at, error_summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        kernel_release,
                        json.dumps(package_ids),
                        1 if is_booted else 0,
                        1 if is_fallback else 0,
                        estimated_freed_bytes,
                        actual_freed_bytes,
                        snapshot_tool,
                        snapshot_id,
                        1 if snapshot_taken else 0,
                        status,
                        started_at or now,
                        finished_at or now,
                        error_summary,
                    ),
                )
                return cursor.lastrowid or 0

    def record_appimage_integration(
        self,
        binary_path: str,
        desktop_path: str,
        display_name: str,
        backup_desktop_path: Optional[str] = None,
        status: str = "integrated",
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO appimage_integrations (
                        binary_path, desktop_path, display_name,
                        backup_desktop_path, status, created_at, last_verified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        binary_path,
                        desktop_path,
                        display_name,
                        backup_desktop_path,
                        status,
                        now,
                        now,
                    ),
                )
                return cursor.lastrowid or 0

    def record_self_update(
        self,
        from_version: str,
        to_version: str,
        release_url: Optional[str] = None,
        download_sha256: Optional[str] = None,
        verified: bool = False,
        rollback_artefact_path: Optional[str] = None,
        status: str = "success",
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        error_summary: Optional[str] = None,
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO self_updates (
                        from_version, to_version, release_url, download_sha256,
                        verified, rollback_artefact_path, status, started_at, finished_at, error_summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        from_version,
                        to_version,
                        release_url,
                        download_sha256,
                        1 if verified else 0,
                        rollback_artefact_path,
                        status,
                        started_at or now,
                        finished_at or now,
                        error_summary,
                    ),
                )
                return cursor.lastrowid or 0
