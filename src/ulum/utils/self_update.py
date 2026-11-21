import json
import os
import re
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

            # Find .deb download URL in release assets
            deb_url = None
            deb_name = None
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".deb"):
                    deb_url = asset.get("browser_download_url")
                    deb_name = name
                    break

            return {
                "success": True,
                "current_version": cur_version,
                "latest_version": latest_version,
                "tag_name": tag_name,
                "update_available": update_available,
                "release_name": data.get("name", tag_name),
                "release_notes": data.get("body", ""),
                "release_url": data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"),
                "download_url": deb_url,
                "deb_filename": deb_name,
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
    def apply_update(cls, download_url: str) -> ExecutionResult:
        """Downloads the new .deb release and installs it using apt-get."""
        if not download_url.startswith("https://"):
            return ExecutionResult(success=False, exit_code=1, stderr="Invalid download URL")

        temp_dir = tempfile.mkdtemp(prefix="ulum_update_")
        target_deb = Path(temp_dir) / "ulum_latest.deb"

        logger.info("Downloading ULUM update from %s...", download_url)
        try:
            req = urllib.request.Request(download_url, headers={"User-Agent": f"ULUM/{__version__}"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(target_deb, "wb") as out_file:
                out_file.write(resp.read())

            if not target_deb.exists() or target_deb.stat().st_size < 1000:
                return ExecutionResult(
                    success=False,
                    exit_code=1,
                    stderr="Downloaded package is empty or corrupt.",
                    error_summary="Package download failed",
                )

            logger.info("Installing new package: %s", target_deb)
            # Use apt-get install --reinstall -y /path/to/deb
            res = run_cmd(
                ["apt-get", "install", "--reinstall", "-y", str(target_deb)],
                require_root=True,
                env={"DEBIAN_FRONTEND": "noninteractive"},
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
                os.rmdir(temp_dir)
            except Exception:
                pass
