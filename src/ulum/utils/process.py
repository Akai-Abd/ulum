import os
import shutil
import subprocess
from typing import Sequence
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
) -> subprocess.CompletedProcess[str]:
    full_cmd = list(cmd)
    if require_root and not is_root():
        if not command_exists("sudo"):
            raise PermissionError("Root privileges required but 'sudo' was not found.")
        full_cmd = ["sudo"] + full_cmd

    logger.debug("Executing: %s", " ".join(full_cmd))
    try:
        result = subprocess.run(
            full_cmd,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
            check=check,
        )
        return result
    except subprocess.TimeoutExpired as e:
        logger.error("Command timed out after %ds: %s", timeout, " ".join(full_cmd))
        raise
    except FileNotFoundError as e:
        logger.error("Binary not found: %s", full_cmd[0] if full_cmd else "")
        raise
