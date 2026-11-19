import http.server
import json
import os
import socketserver
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse
from ulum import __version__
from ulum.cli.display import format_bytes
from ulum.core.config import UlumConfig
from ulum.core.orchestrator import Orchestrator
from ulum.core.system import detect_package_managers, get_system_info
from ulum.db.repository import Repository
from ulum.removal.leftovers import LeftoverScanner
from ulum.removal.safety import SafetyValidator
from ulum.utils.logging import logger

WEB_DIR = Path(__file__).parent / "web"

class UlumApiHandler(http.server.BaseHTTPRequestHandler):
    repo: Repository
    config: UlumConfig
    orchestrator: Orchestrator

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(f"HTTP: {format % args}")

    def send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            html_file = WEB_DIR / "index.html"
            if html_file.exists():
                content = html_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Web assets not found")
            return

        if path == "/api/stats":
            info = get_system_info()
            apps = self.repo.get_applications()
            upds = self.repo.get_updates()
            cands = self.repo.get_cleanup_candidates(confidence="verified")

            counts_by_source: Dict[str, int] = {"apt": 0, "flatpak": 0, "snap": 0}
            for u in upds:
                src = u.get("source", "").lower()
                if src in counts_by_source:
                    counts_by_source[src] += 1

            total_leftover_bytes = sum(c.get("estimated_size", 0) for c in cands)

            data = {
                "version": __version__,
                "distro_name": info.distro_name,
                "distro_version": info.distro_version,
                "arch": info.arch,
                "installed_count": len(apps),
                "updates_count": len(upds),
                "updates_by_source": counts_by_source,
                "leftovers_count": len(cands),
                "leftovers_size": format_bytes(total_leftover_bytes) if total_leftover_bytes > 0 else "0 B",
            }
            self.send_json(data)
            return

        if path == "/api/inventory":
            source_filter = query.get("source", [None])[0]
            apps = self.repo.get_applications(source=source_filter)
            data = [
                {
                    "qualified_id": a.qualified_id,
                    "package_id": a.package_id,
                    "name": a.display_name,
                    "source": a.source.value,
                    "scope": a.source_scope.value,
                    "version": a.installed_version,
                    "install_location": a.install_location,
                }
                for a in apps
            ]
            self.send_json(data)
            return

        if path == "/api/updates":
            upds = self.repo.get_updates()
            self.send_json(upds)
            return

        if path == "/api/leftovers":
            cands = self.repo.get_cleanup_candidates()
            for c in cands:
                c["formatted_size"] = format_bytes(c.get("estimated_size", 0))
            self.send_json(cands)
            return

        if path == "/api/history":
            upd_hist = self.repo.get_update_history(limit=50)
            rem_hist = self.repo.get_removal_history(limit=50)
            self.send_json({"update_history": upd_hist, "removal_history": rem_hist})
            return

        if path == "/api/diagnostics":
            info = get_system_info()
            mgrs = detect_package_managers()
            self.send_json({
                "system": {
                    "distro_name": info.distro_name,
                    "distro_version": info.distro_version,
                    "distro_id": info.distro_id,
                    "arch": info.arch,
                    "kernel": info.kernel,
                    "is_supported": info.is_supported,
                },
                "package_managers": mgrs,
            })
            return

        if path == "/api/settings":
            from ulum.core.config import get_config_dir
            from ulum.db.database import get_db_path
            self.send_json({
                "enabled_adapters": self.config.enabled_adapters,
                "excluded_packages": self.config.excluded_packages,
                "require_confirmation": self.config.require_confirmation,
                "log_level": self.config.log_level,
                "config_path": str(get_config_dir() / "config.toml"),
                "db_path": str(get_db_path()),
            })
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        if path == "/api/scan":
            counts = self.orchestrator.scan_all()
            self.send_json({"success": True, "counts": counts})
            return

        if path == "/api/check_updates":
            refresh = payload.get("refresh", False)
            upds = self.orchestrator.check_updates(refresh=refresh)
            self.send_json({"success": True, "count": len(upds)})
            return

        if path == "/api/update":
            identifier = payload.get("identifier")
            all_pkgs = payload.get("all", False)
            source = payload.get("source")
            targets = [identifier] if identifier else None
            results = self.orchestrator.execute_updates(targets=targets, source=source, dry_run=False)
            success = all(r.success for _, r in results)
            self.send_json({"success": success})
            return

        if path == "/api/plan_removal":
            identifier = payload.get("identifier", "")
            complete = payload.get("complete", False)
            try:
                app_rec, plan = self.orchestrator.plan_removal(identifier, complete=complete)
                self.send_json({
                    "success": True,
                    "plan": {
                        "qualified_id": plan.application.qualified_id,
                        "complete": plan.complete,
                        "native_command": plan.native_command,
                        "packages_to_remove": plan.packages_to_remove,
                        "cleanup_items": [str(c.path) for c in plan.cleanup_items],
                        "freed_bytes": plan.estimated_freed_bytes,
                        "formatted_freed": format_bytes(plan.estimated_freed_bytes),
                        "safety_warnings": plan.safety_warnings,
                        "is_safe": plan.is_safe,
                    }
                })
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, status=400)
            return

        if path == "/api/execute_removal":
            identifier = payload.get("identifier", "")
            complete = payload.get("complete", False)
            try:
                app_rec, plan = self.orchestrator.plan_removal(identifier, complete=complete)
                res = self.orchestrator.execute_removal(plan, dry_run=False)
                self.send_json({
                    "success": res.success,
                    "exit_code": res.exit_code,
                    "removed_items": res.removed_items,
                    "error_summary": res.error_summary,
                })
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, status=400)
            return

        if path == "/api/scan_leftovers":
            scanner = LeftoverScanner(self.repo, adapters=self.orchestrator.adapters)
            cands = scanner.scan_leftovers()
            self.repo.save_cleanup_candidates(cands, source="system", package_id="<residual>")
            self.send_json({"success": True, "count": len(cands)})
            return

        if path == "/api/cleanup":
            import shutil
            target_path = payload.get("path")
            if target_path:
                cands = [c for c in self.repo.get_cleanup_candidates() if c["path"] == target_path]
            else:
                cands = self.repo.get_cleanup_candidates(confidence="verified")
            deleted = 0
            for c in cands:
                p = Path(c["path"])
                valid, _ = SafetyValidator.validate_cleanup_path(p)
                if valid and p.exists():
                    try:
                        if p.is_dir() and not p.is_symlink():
                            shutil.rmtree(p)
                        else:
                            p.unlink()
                        self.repo.mark_candidate_removed(str(p))
                        deleted += 1
                    except Exception as e:
                        logger.error("Failed to delete %s: %s", p, e)
            self.send_json({"success": True, "deleted": deleted})
            return

        if path == "/api/settings":
            from ulum.core.config import UlumConfig, save_config
            enabled = payload.get("enabled_adapters", ["apt", "flatpak", "snap"])
            excluded = payload.get("excluded_packages", [])
            req_confirm = bool(payload.get("require_confirmation", True))
            log_lvl = payload.get("log_level", "INFO")
            new_cfg = UlumConfig(
                enabled_adapters=enabled,
                excluded_packages=excluded,
                require_confirmation=req_confirm,
                log_level=log_lvl,
            )
            save_config(new_cfg)
            self.config.enabled_adapters = enabled
            self.config.excluded_packages = excluded
            self.config.require_confirmation = req_confirm
            self.config.log_level = log_lvl
            self.send_json({"success": True})
            return

        self.send_error(404, "Endpoint not found")

def create_server(repo: Repository, config: UlumConfig, orchestrator: Orchestrator, host: str = "127.0.0.1", port: int = 0) -> socketserver.TCPServer:
    class BoundHandler(UlumApiHandler):
        pass

    BoundHandler.repo = repo
    BoundHandler.config = config
    BoundHandler.orchestrator = orchestrator

    # Re-use address to avoid lingering port bindings
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer((host, port), BoundHandler)
    return server
