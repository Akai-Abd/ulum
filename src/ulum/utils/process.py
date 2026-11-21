import os
import shutil
import subprocess
import sys
from typing import Optional, Sequence
from ulum.utils.logging import logger

def command_exists(binary: str) -> bool:
    return shutil.which(binary) is not None

def is_root() -> bool:
    return os.geteuid() == 0

def run_cmd(
    cmd: Sequence[str],
    require_root: bool = False,
    timeout: int = 300,
    check: bool = False,
    capture_output: bool = True,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess[str]:
    full_cmd = list(cmd)
    if require_root and not is_root():
        can_sudo_nopasswd = False
        if command_exists("sudo"):
            try:
                can_sudo_nopasswd = (
                    subprocess.run(
                        ["sudo", "-n", "true"],
                        capture_output=True,
                        timeout=5,
                    ).returncode == 0
                )
            except Exception:
                can_sudo_nopasswd = False

        is_gui_or_non_tty = (not sys.stdin.isatty()) or bool(
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )

        if not can_sudo_nopasswd and is_gui_or_non_tty and command_exists("pkexec"):
            prog = shutil.which(full_cmd[0]) or full_cmd[0]
            full_cmd = ["pkexec", prog] + full_cmd[1:]
        elif command_exists("sudo"):
            full_cmd = ["sudo"] + full_cmd
        elif command_exists("pkexec"):
            prog = shutil.which(full_cmd[0]) or full_cmd[0]
            full_cmd = ["pkexec", prog] + full_cmd[1:]
        else:
            raise PermissionError("Root privileges required but neither 'sudo' nor 'pkexec' was found.")

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    logger.debug("Executing: %s", " ".join(full_cmd))
    try:
        result = subprocess.run(
            full_cmd,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
            check=check,
            env=full_env,
        )
        return result
    except subprocess.TimeoutExpired as e:
        logger.error("Command timed out after %ds: %s", timeout, " ".join(full_cmd))
        raise
    except FileNotFoundError as e:
        logger.error("Binary not found: %s", full_cmd[0] if full_cmd else "")
        raise
