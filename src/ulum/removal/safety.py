import os
from pathlib import Path
from typing import List, Tuple

SYSTEM_BLACKLIST = {
    Path("/"),
    Path("/bin"),
    Path("/boot"),
    Path("/dev"),
    Path("/etc"),
    Path("/lib"),
    Path("/lib64"),
    Path("/opt"),
    Path("/proc"),
    Path("/root"),
    Path("/run"),
    Path("/sbin"),
    Path("/sys"),
    Path("/usr"),
    Path("/var"),
}

def get_allowed_cleanup_bases() -> List[Path]:
    home = Path.home().resolve()
    return [
        (home / ".config").resolve(),
        (home / ".cache").resolve(),
        (home / ".local" / "share").resolve(),
        (home / ".local" / "state").resolve(),
        (home / ".var" / "app").resolve(),
        (home / "snap").resolve(),
    ]

def get_protected_user_paths() -> List[Path]:
    home = Path.home().resolve()
    return [
        home,
        (home / "Desktop").resolve(),
        (home / "Documents").resolve(),
        (home / "Downloads").resolve(),
        (home / "Music").resolve(),
        (home / "Pictures").resolve(),
        (home / "Videos").resolve(),
        (home / ".bashrc").resolve(),
        (home / ".profile").resolve(),
        (home / ".bash_profile").resolve(),
    ]

class SafetyValidator:
    @staticmethod
    def validate_cleanup_path(path: Path | str) -> Tuple[bool, str]:
        target = Path(path).expanduser()
        
        # Check system blacklist
        for sys_dir in SYSTEM_BLACKLIST:
            try:
                if target.resolve() == sys_dir.resolve():
                    return False, f"Path '{target}' is a critical system directory."
            except Exception:
                pass

        # Check protected user directories
        for user_dir in get_protected_user_paths():
            try:
                if target.resolve() == user_dir.resolve():
                    return False, f"Path '{target}' is a protected user directory."
            except Exception:
                pass

        # Check containment within allowed cleanup bases
        try:
            resolved = target.resolve()
        except Exception as e:
            return False, f"Cannot resolve path '{target}': {e}"

        allowed_bases = get_allowed_cleanup_bases()
        is_contained = False
        for base in allowed_bases:
            if resolved == base:
                return False, f"Cannot delete base directory '{base}'."
            if base in resolved.parents:
                is_contained = True
                break

        if not is_contained:
            return False, f"Path '{target}' is outside permitted cleanup locations (~/.config, ~/.cache, ~/.local/share, ~/.var/app, ~/snap)."

        # Check symlink boundary escapes
        if target.is_symlink():
            try:
                link_dest = target.readlink()
                resolved_link = target.resolve()
                if not any(base in resolved_link.parents or resolved_link == base for base in allowed_bases):
                    return False, f"Symlink '{target}' points outside allowed cleanup boundaries (targets {resolved_link})."
            except Exception as e:
                return False, f"Failed checking symlink target: {e}"

        return True, ""
