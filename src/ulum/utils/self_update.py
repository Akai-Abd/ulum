import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from ulum import __version__
from ulum.core.models import ExecutionResult
from ulum.utils.logging import logger
from ulum.utils.process import run_cmd

GITHUB_REPO = "Akai-Abd/ulum"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def parse_version_tuple(v: str) -> Tuple[int, ...]:
    nums = [int(n) for n in re.findall(r"\d+", v)]
    return tuple(nums) if nums else (0, 0, 0)


class SelfUpdater:
    """Checks for new ULUM application releases on GitHub and handles automated upgrades."""

    @classmethod
    def check_latest_release(cls, current_version: Optional[str] = None, timeout: int = 5) -> Dict[str, Any]:
        """Queries GitHub API to determine if a newer ULUM release exists."""
        cur_version = current_version or __version__
        req = urllib.request.Request(
            API_URL,
            headers={
                "User-Agent": f"ULUM/{cur_version}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"GitHub returned HTTP status {response.status}",
                        "current_version": cur_version,
                    }
                data = json.loads(response.read().decode("utf-8"))

            tag_name = data.get("tag_name", "").strip()
            latest_version = tag_name.lstrip("v")
            current_tuple = parse_version_tuple(cur_version)
            latest_tuple = parse_version_tuple(latest_version)

            update_available = latest_tuple > current_tuple

            # Find .deb download URL and checksum in release assets
            deb_url = None
            deb_name = None
            sha256_val = None

            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".deb"):
                    deb_url = asset.get("browser_download_url")
                    deb_name = name

            body = data.get("body", "")
            sha_match = re.search(r"\b([a-fA-F0-9]{64})\b", body)
            if sha_match:
                sha256_val = sha_match.group(1).lower()

            return {
                "success": True,
                "current_version": cur_version,
                "latest_version": latest_version,
                "tag_name": tag_name,
                "update_available": update_available,
                "release_name": data.get("name", tag_name),
                "release_notes": body,
                "release_url": data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"),
                "download_url": deb_url,
                "deb_filename": deb_name,
                "sha256": sha256_val,
                "published_at": data.get("published_at", ""),
            }
        except urllib.error.URLError as e:
            logger.warning("Could not check ULUM updates (offline or network error): %s", e)
            return {
                "success": False,
                "error": f"Network unreachable: {e.reason if hasattr(e, 'reason') else e}",
                "current_version": cur_version,
                "update_available": False,
            }
        except Exception as e:
            logger.error("Error checking ULUM updates: %s", e)
            return {
                "success": False,
                "error": str(e),
                "current_version": cur_version,
                "update_available": False,
            }

    @classmethod
    def apply_update(
        cls,
        download_url: str,
        expected_sha256: Optional[str] = None,
        require_sha256: bool = True,
    ) -> ExecutionResult:
        """Downloads the new .deb release, verifies SHA256, and installs it safely."""
        if not download_url.startswith("https://"):
            return ExecutionResult(success=False, exit_code=1, stderr="Invalid download URL")

        if require_sha256 and not expected_sha256:
            return ExecutionResult(
                success=False,
                exit_code=1,
                stderr="SHA256 checksum is mandatory in v0.4. Refusing to install unverified package.",
                error_summary="Unverified package: SHA256 missing",
            )

        temp_dir = tempfile.mkdtemp(prefix="ulum_update_")
        target_deb = Path(temp_dir) / "ulum_latest.deb"

        logger.info("Downloading ULUM update from %s...", download_url)
        try:
            req = urllib.request.Request(download_url, headers={"User-Agent": f"ULUM/{__version__}"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(target_deb, "wb") as out_file:
                content = resp.read()
                out_file.write(content)

            if not target_deb.exists() or target_deb.stat().st_size < 1000:
                return ExecutionResult(
                    success=False,
                    exit_code=1,
                    stderr="Downloaded package is empty or corrupt.",
                    error_summary="Package download failed",
                )

            # Mandatory SHA256 verification
            hasher = hashlib.sha256(content)
            actual_sha = hasher.hexdigest().lower()
            if expected_sha256:
                if actual_sha != expected_sha256.lower().strip():
                    target_deb.unlink(missing_ok=True)
                    err_msg = (
                        f"SHA256 checksum mismatch! Expected: {expected_sha256.lower().strip()}, "
                        f"Got: {actual_sha}. Refusing installation."
                    )
                    logger.critical(err_msg)
                    return ExecutionResult(
                        success=False,
                        exit_code=1,
                        stderr=err_msg,
                        error_summary="Checksum mismatch: package refused",
                    )
                logger.info("SHA256 checksum verified successfully: %s", actual_sha)

            # Prepare rollback artifact directory
            rollback_dir = Path.home() / ".local" / "share" / "ulum" / "rollback"
            rollback_dir.mkdir(parents=True, exist_ok=True)

            logger.info("Installing new package: %s", target_deb)
            res = run_cmd(
                ["apt-get", "install", "--reinstall", "-y", str(target_deb)],
                require_root=True,
                env={"DEBIAN_FRONTEND": "noninteractive"},
            )

            if res.returncode == 0:
                smoke = run_cmd(["ulum", "version"])
                if smoke.returncode != 0:
                    return ExecutionResult(
                        success=False,
                        exit_code=1,
                        stderr="New version failed launch smoke test! Rollback recommended.",
                        error_summary="Launch smoke test failed",
                    )

            return ExecutionResult(
                success=(res.returncode == 0),
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                error_summary=res.stderr if res.returncode != 0 else None,
            )
        except Exception as e:
            logger.error("Failed executing self update: %s", e)
            return ExecutionResult(
                success=False,
                exit_code=1,
                stderr=str(e),
                error_summary=f"Update failed: {e}",
            )
        finally:
            try:
                if target_deb.exists():
                    target_deb.unlink()
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
