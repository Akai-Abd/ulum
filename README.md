# 🐧 ULUM — Universal Linux Update Manager

<div align="center">

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Linux%20(Mint%20%7C%20Ubuntu)-orange.svg?style=flat-square&logo=linux)](https://github.com/Akai-Abd/ulum)
[![Package Managers](https://img.shields.io/badge/sources-APT%20%7C%20Flatpak%20%7C%20Snap-success.svg?style=flat-square)](https://github.com/Akai-Abd/ulum)
[![GUI](https://img.shields.io/badge/GUI-GTK3%20%2B%20WebKit2%20Dashboard-purple.svg?style=flat-square)](https://github.com/Akai-Abd/ulum)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Built by](https://img.shields.io/badge/Built%20by-Abdurrahman-7c3aed.svg?style=flat-square&logo=github)](https://github.com/Akai-Abd)

**An intelligent, multi-source package manager and safe uninstaller for Linux.**  
Seamlessly orchestrate software updates and clean removals across **APT**, **Flatpak**, and **Snap** from a unified CLI and modern glassmorphic desktop GUI.

[Features](#-key-features) • [Quickstart](#-quickstart) • [CLI Reference](#-cli-reference) • [GUI Dashboard](#-desktop-gui) • [Safety Architecture](#-safety--residual-protection) • [Contributing](#-development)

---

</div>

## 🌟 Key Features

- **Unified Multi-Source Updates**: Check and upgrade packages across system repositories (APT), sandboxed runtimes (Flatpak), and containerized snaps (Snap) in one command.
- **Safe Application Removal**: Complete and standard uninstallation workflows powered by native package managers with dependency analysis and reverse-dependency protection.
- **Residual Leftover Detection**: Scans `~/.var/app`, `~/snap`, `~/.config`, and `~/.cache` for orphaned folders and configuration files left behind after uninstalls, with built-in system directory protection.
- **Modern Glassmorphic Desktop GUI**: Dark-mode glassmorphic dashboard built with GTK3 and embedded WebKit2 (featuring auto-fallback to native GTK controls).
- **Native Dependency Inspection**: Inspect package dependencies and installed reverse-dependencies before modifying the system.
- **Local SQLite Tracking**: Maintains a persistent local inventory and auditable history of updates, removals, and discovered cleanup candidates.
- **Dry-Run Simulation**: Preview exactly what packages will be updated or deleted before making any changes.

---

## 🏗️ Architecture

```
                                  ┌─────────────────────────────┐
                                  │      ULUM Unified Core      │
                                  │ (Orchestrator, DB, Config)  │
                                  └──────────────┬──────────────┘
                                                 │
                   ┌─────────────────────────────┼─────────────────────────────┐
                   │                             │                             │
                   ▼                             ▼                             ▼
         ┌───────────────────┐         ┌───────────────────┐         ┌───────────────────┐
         │    APT Adapter    │         │  Flatpak Adapter  │         │   Snap Adapter    │
         │ (dpkg / apt-get)  │         │ (flatpak runtime) │         │   (snapd daemon)  │
         └───────────────────┘         └───────────────────┘         └───────────────────┘
```

---

## 🚀 Quickstart

### Prerequisites

- Linux (Ubuntu 24.04+ or Linux Mint 22+)
- Python 3.12 or newer
- GTK3 and WebKit2 (`gir1.2-webkit2-4.1` for desktop GUI)

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Akai-Abd/ulum.git
cd ulum

# Create virtual environment & install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Verify Environment

```bash
ulum doctor
```

```text
Running ULUM Health Diagnostics...

Distribution: Linux Mint 22.3
Supported Platform: Yes

Package Managers:
  • APT: Available
  • FLATPAK: Available
  • SNAP: Available

Database Storage: ~/.local/share/ulum/ulum.db (Writable)
Privilege Escalation (sudo/root): OK

✓ Diagnostic check complete.
```

---

## 💻 CLI Reference

| Command | Description |
| :--- | :--- |
| `ulum doctor` | Diagnose distro compatibility, package managers, and storage health. |
| `ulum scan` | Index all installed packages across APT, Flatpak, and Snap into local inventory. |
| `ulum check [--refresh]` | Query available updates across all active package managers. |
| `ulum list [--updates]` | Display installed applications or pending updates in rich tables. |
| `ulum info <id>` | Inspect metadata for a package (e.g. `apt:curl` or `flatpak:org.mozilla.firefox`). |
| `ulum update --all` | Update all eligible packages across all sources. |
| `ulum update <id>` | Update a specific application through its native manager. |
| `ulum update --dry-run` | Preview proposed updates without modifying the system. |
| `ulum remove <id>` | Perform standard native uninstallation. |
| `ulum remove <id> --complete` | Complete removal (purge configs and verified application data). |
| `ulum leftovers` | Discover orphaned residual configuration and data directories. |
| `ulum cleanup [--yes]` | Review and permanently delete verified residual leftovers. |
| `ulum dependencies <id>` | Inspect native package dependencies and reverse dependencies. |
| `ulum history` | View historical record of software updates. |
| `ulum removal-history` | View historical record of package uninstalls and deletions. |

---

## 🖥️ Desktop GUI

Launch the graphical dashboard:

```bash
ulum gui
# or execute directly:
./run_gui.sh
```

- **Live Updates Tab**: View pending updates across all sources and update individually or in bulk.
- **Installed Software Tab**: Search, filter by source, inspect dependencies, or trigger standard and complete uninstalls.
- **Leftovers & Cleanup Tab**: Browse residual directories with confidence ratings and inspect exact disk usage before deletion.
- **Operation History Tab**: Track past system operations, exit codes, and timestamps.
- **Settings Tab**: Toggle individual package managers, exclude packages from auto-updates, and configure confirmation prompts.

---

## 🛡️ Safety & Residual Protection

ULUM treats user data and system stability with the highest priority:

1. **System Directory Blacklist**: Never modifies or deletes core system roots (`/`, `/bin`, `/boot`, `/etc`, `/usr`, `/var`, etc.).
2. **Protected User Directories**: Shields personal directories (`~/Documents`, `~/Downloads`, `~/Desktop`, `.bashrc`, etc.) from cleanup routines.
3. **Boundary & Symlink Containment**: Residual scanning is strictly constrained to safe candidate paths (`~/.var/app`, `~/snap`, `~/.config`, `~/.cache`). Symlinks targeting locations outside permitted bases are automatically rejected.
4. **Active Verification**: Before any leftover folder is recommended for deletion, ULUM validates with native package managers (`flatpak info`, `snap list`, `dpkg`) to ensure the owning application is not currently installed.
5. **Prompt Confirmation**: Interactive CLI prompts and GUI confirmation modals summarize commands, exact file paths, and estimated freed space before any destructive action.

---

## 🧪 Development & Testing

Run the comprehensive unit and integration test suite:

```bash
source .venv/bin/activate
pytest -v
```

```text
tests/integration/test_cli.py ........
tests/unit/test_adapters.py ....
tests/unit/test_db.py ....
tests/unit/test_executor.py ..
tests/unit/test_gui.py .
tests/unit/test_leftovers.py ..
tests/unit/test_planner.py ..
tests/unit/test_safety.py .....
tests/unit/test_server.py .
tests/unit/test_system_and_config.py ..

============================== 28 passed ==============================
```

---

## 👨‍💻 Author

Designed and built by **[Abdurrahman](https://github.com/Akai-Abd)**.

---

## 📄 License

Distributed under the [MIT License](LICENSE). Built with Python, Typer, Rich, GTK3, and WebKit2.
