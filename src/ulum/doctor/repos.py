import datetime
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from ulum.utils.logging import logger
from ulum.utils.process import command_exists, run_cmd


class AptRepoDoctor:
    """Diagnoses and repairs broken, obsolete, or 404 APT repositories."""

    SOURCES_DIR = Path("/etc/apt/sources.list.d")
    PRIMARY_SOURCES = Path("/etc/apt/sources.list")

    @classmethod
    def check_broken_sources(cls, allow_list: Optional[List[str]] = None) -> Tuple[List[Dict[str, Any]], str]:
        """Runs apt-get update to detect repositories returning 404 or missing release files."""
        if not command_exists("apt-get"):
            return [], "APT is not available on this system."

        res = run_cmd(["apt-get", "update"], require_root=True)
        output = (res.stdout or "") + "\n" + (res.stderr or "")

        broken_urls: List[Dict[str, str]] = []

        # Patterns for 404 or broken release files
        p404 = re.compile(r"Failed to fetch\s+([^\s]+)\s+404\s+Not Found", re.IGNORECASE)
        p_no_release = re.compile(r"The repository '([^\s]+)[^']*' does not have a Release file", re.IGNORECASE)
        p_gpg = re.compile(r"GPG error:\s+([^\s]+)", re.IGNORECASE)

        for line in output.splitlines():
            line = line.strip()
            m1 = p404.search(line)
            if m1:
                broken_urls.append({"url": m1.group(1), "reason": "404 Not Found"})
                continue
            m2 = p_no_release.search(line)
            if m2:
                broken_urls.append({"url": m2.group(1), "reason": "Missing Release file (obsolete distro)"})
                continue
            m3 = p_gpg.search(line)
            if m3:
                broken_urls.append({"url": m3.group(1), "reason": "GPG / key verification failure"})

        matched_entries = cls.find_source_files_for_urls(broken_urls, allow_list=allow_list)
        return matched_entries, output

    @classmethod
    def _normalize_url(cls, url: str) -> str:
        """Strips protocol and trailing parts for fuzzy matching in sources files."""
        clean = re.sub(r"^https?://", "", url).split("/dists/")[0].strip("/")
        return clean

    @classmethod
    def find_source_files_for_urls(
        cls, broken_urls: List[Dict[str, str]], allow_list: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Maps detected broken URLs back to specific files and line numbers in /etc/apt."""
        results: List[Dict[str, Any]] = []
        if not broken_urls:
            return results

        allow_patterns = allow_list or []

        target_files: List[Path] = []
        if cls.PRIMARY_SOURCES.exists():
            target_files.append(cls.PRIMARY_SOURCES)
        if cls.SOURCES_DIR.exists():
            for p in cls.SOURCES_DIR.glob("*.list"):
                target_files.append(p)
            for p in cls.SOURCES_DIR.glob("*.sources"):
                target_files.append(p)

        for target in target_files:
            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                logger.warning("Could not read %s: %s", target, e)
                continue

            lines = content.splitlines()
            for idx, line in enumerate(lines, start=1):
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue

                # Check allow-list
                if any(allow_pat in raw for allow_pat in allow_patterns):
                    continue

                for b in broken_urls:
                    url_key = cls._normalize_url(b["url"])
                    if url_key and url_key in raw:
                        results.append({
                            "file": str(target),
                            "line_number": idx,
                            "line_content": line,
                            "url": b["url"],
                            "reason": b["reason"],
                            "file_type": "sources" if target.suffix == ".sources" else "list",
                        })
                        break

        return results

    @classmethod
    def create_backup(cls, file_path: Path) -> Path:
        """Creates a timestamped backup before modifying any sources list."""
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = file_path.parent / f"{file_path.name}.ulum-backup-{ts}"
        try:
            if os.geteuid() == 0 or os.access(file_path.parent, os.W_OK):
                shutil.copy2(file_path, backup_path)
            else:
                run_cmd(["cp", str(file_path), str(backup_path)], require_root=True)
            logger.info("Created repository backup: %s", backup_path)
            return backup_path
        except Exception as e:
            logger.warning("Failed to create local backup in sources directory: %s", e)
            fallback_dir = Path.home() / ".local" / "share" / "ulum" / "backups"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            fallback_backup = fallback_dir / f"{file_path.name}.ulum-backup-{ts}"
            shutil.copy2(file_path, fallback_backup)
            return fallback_backup

    @classmethod
    def disable_broken_entry(cls, entry: Dict[str, Any], dry_run: bool = False) -> Tuple[bool, str]:
        """Disables the broken entry by commenting out the line after backing up."""
        file_path = Path(entry["file"])
        if not file_path.exists():
            return False, f"File {file_path} does not exist"

        if dry_run:
            return True, f"Dry-run: Would disable entry in {file_path}:{entry['line_number']}"

        try:
            # Create safety backup first
            backup_path = cls.create_backup(file_path)
            entry["backup_path"] = str(backup_path)

            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            target_line_idx = entry["line_number"] - 1

            if 0 <= target_line_idx < len(lines):
                orig_line = lines[target_line_idx]
                if not orig_line.strip().startswith("#"):
                    lines[target_line_idx] = f"# DISABLED BY ULUM ({entry.get('reason', 'broken')}): {orig_line}"
                    new_content = "\n".join(lines) + "\n"
                    # Write with root permissions if needed
                    if os.geteuid() == 0 or os.access(file_path, os.W_OK):
                        file_path.write_text(new_content, encoding="utf-8")
                    else:
                        import tempfile
                        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
                            tf.write(new_content)
                            tmp_name = tf.name
                        run_cmd(["cp", tmp_name, str(file_path)], require_root=True)
                        os.unlink(tmp_name)
                    return True, f"Disabled broken repository in {file_path.name}"
            return False, "Line number out of range or already disabled"
        except Exception as e:
            return False, f"Failed updating {file_path}: {e}"

    @classmethod
    def restore_all_backups(cls) -> Dict[str, Any]:
        """Restores repository files from their most recent .ulum-backup-* files."""
        search_dirs = [cls.SOURCES_DIR, cls.PRIMARY_SOURCES.parent, Path.home() / ".local" / "share" / "ulum" / "backups"]
        restored = []
        errors = []

        seen_targets = set()
        for sdir in search_dirs:
            if not sdir.exists():
                continue
            backup_files = sorted(sdir.glob("*.ulum-backup-*"), reverse=True)
            for bfile in backup_files:
                # Derive original target name: foo.list.ulum-backup-timestamp -> foo.list
                orig_name = re.sub(r"\.ulum-backup-.*$", "", bfile.name)
                target_file = sdir / orig_name
                if not target_file.exists() and sdir == cls.SOURCES_DIR:
                    pass
                if str(target_file) in seen_targets:
                    continue  # already restored from newer backup

                try:
                    if os.geteuid() == 0 or os.access(target_file.parent, os.W_OK):
                        shutil.copy2(bfile, target_file)
                    else:
                        run_cmd(["cp", str(bfile), str(target_file)], require_root=True)
                    seen_targets.add(str(target_file))
                    restored.append({"target": str(target_file), "from_backup": str(bfile)})
                    logger.info("Restored %s from %s", target_file, bfile)
                except Exception as e:
                    errors.append(f"Failed restoring {target_file}: {e}")

        return {
            "restored_count": len(restored),
            "restored_files": restored,
            "errors": errors,
            "success": len(errors) == 0,
        }

    @classmethod
    def fix_all_broken(cls, dry_run: bool = False, allow_list: Optional[List[str]] = None) -> Dict[str, Any]:
        """Scans and disables all broken APT repositories."""
        entries, _ = cls.check_broken_sources(allow_list=allow_list)
        disabled = []
        errors = []

        for entry in entries:
            ok, msg = cls.disable_broken_entry(entry, dry_run=dry_run)
            if ok:
                disabled.append(entry)
            else:
                errors.append(msg)

        return {
            "found_count": len(entries),
            "disabled_count": len(disabled),
            "disabled_entries": disabled,
            "errors": errors,
            "success": len(errors) == 0,
        }
