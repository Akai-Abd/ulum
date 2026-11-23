# 🐧 ULUM — Universal Linux Update Manager

<div align="center">

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Linux%20(Mint%20%7C%20Ubuntu)-orange.svg?style=flat-square&logo=linux)](https://github.com/Akai-Abd/ulum)
[![Package Managers](https://img.shields.io/badge/sources-APT%20%7C%20Flatpak%20%7C%20Snap%20%7C%20AppImage-success.svg?style=flat-square)](https://github.com/Akai-Abd/ulum)
[![GUI](https://img.shields.io/badge/GUI-Native%20GTK%20Dashboard-purple.svg?style=flat-square)](https://github.com/Akai-Abd/ulum)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Built by](https://img.shields.io/badge/Built%20by-Abdurrahman-7c3aed.svg?style=flat-square&logo=github)](https://github.com/Akai-Abd)

**An intelligent, multi-source package manager and safe uninstaller for Linux.**  
Seamlessly orchestrate software updates and clean removals across **APT**, **Flatpak**, **Snap**, and **AppImage** from a unified CLI and modern glassmorphic desktop GUI.

[Features](#-key-features) • [Quickstart](#-quickstart) • [CLI Reference](#-cli-reference) • [GUI Dashboard](#-desktop-gui) • [Safety Architecture](#-safety--residual-protection) • [Contributing](#-development)

---

</div>

## 🌟 Key Features

- **Unified Multi-Source Updates**: Check and upgrade packages across system repositories (APT), sandboxed runtimes (Flatpak), containerized snaps (Snap), and standalone binaries (AppImage) in one command.
- **Concurrent Async Engine with Timeouts**: Scans all enabled package sources in parallel with 30-second bounded timeouts and 1-hour inventory caching.
- **Security-First Tagging (`--security-only`)**: Identifies APT security updates directly from `-security` pocket origins and updates critical vulnerabilities first (`ulum update --security-only`).
- **Broken PPA & 404 Repo Auto-Fix**: Diagnoses dead or expired repositories in `/etc/apt/sources.list.d/` and comments them out safely (`ulum doctor --fix-repos` or 1-click in GUI Diagnostics).
- **Obsolete Kernel & `/boot` Partition Saver**: Intelligently identifies and purges obsolete Linux kernels and residual config files while strictly guarding active booted (`uname -r`) and fallback kernels (`ulum cleanup --kernels`).
- **Standalone AppImage Desktop Integrator**: Auto-discovers AppImages in `~/Downloads` and `~/Applications`, applies executable bits (`chmod +x`), and registers standard XDG desktop launchers in your Start Menu (`ulum integrate --all`).
- **Download Size & Metered Connection Warning**: Calculates pre-upgrade bandwidth consumption and warns before downloading large runtime updates (> 1 GB) on metered or mobile connections.
- **In-App Self-Updater in Settings Dashboard**: Check GitHub releases, preview release notes, and upgrade ULUM directly from the GUI Settings dashboard or CLI (`ulum self-update`).
- **Seamless Root & Polkit Execution**: Integrated PolicyKit (`pkexec`) authorization and X11 display access forwarding for smooth, passwordless in-app GUI updates without terminal locks.
- **Automated Health Repair**: Interrupted APT lock and dpkg state auto-repair with `ulum doctor --fix`.
- **Scheduled Background Updates**: Native user-level systemd timer and desktop notifications (`ulum schedule --install`).
- **Safe Application Removal**: Complete and standard uninstallation workflows powered by native package managers with dependency analysis and reverse-dependency protection.
- **Residual Leftover Detection**: Scans `~/.var/app`, `~/snap`, `~/.config`, and `~/.cache` for orphaned folders and configuration files left behind after uninstalls, with built-in system directory protection.
- **Native Desktop GUI**: Fast, responsive desktop dashboard built with native GTK widgets featuring 7 dedicated views, transparent Health Score breakdown (0-100), and instant startup without webview or browser engine overhead.
- **P0 Safety Hardening**: Pre-modification repo backups with 1-click restore (`ulum doctor --restore-repos`), strict 2-kernel minimum check with DKMS & snapshot warnings, SHA256 checksum verification on self-updates, and AppImage unintegration (`ulum integrate --remove <id>`).
- **Comprehensive 8-Point Health Diagnostics (`ulum doctor [--json]`)**: Full-system health audit inspecting OS distribution, package managers, repository health, `/boot` partition, SQLite schema integrity, stale lock resolution, inventory scan freshness, and release updates.
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
                    ┌─────────────────┬──────────────┴──────────────┬─────────────────┐
                    │                 │                             │                 │
                    ▼                 ▼                             ▼                 ▼
          ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
          │    APT Adapter    │ │  Flatpak Adapter  │ │   Snap Adapter    │ │ AppImage Adapter  │
          │ (dpkg / apt-get)  │ │ (flatpak runtime) │ │   (snapd daemon)  │ │ (~/Applications)  │
          └───────────────────┘ └───────────────────┘ └───────────────────┘ └───────────────────┘
```

---

## 🚀 Quickstart

### Prerequisites

- Linux (Ubuntu 24.04+ or Linux Mint 22+)
- Python 3.12 or newer
- GTK3 (`gir1.2-gtk-3.0` for native desktop GUI)

### 1. Installation

#### Option A: Debian Package (.deb) — Recommended

Install the pre-built `.deb` package directly:

```bash
sudo dpkg -i ulum_0.4.0_all.deb
# Or from the repository root:
sudo dpkg -i dist/ulum_0.4.0_all.deb
```

#### Option B: From Source (Development)

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
Running ULUM Health Diagnostics (8-Point Checklist)...

✓ 1. Distribution & Kernel: Ubuntu 24.04 (x86_64, Linux 6.8.0-49-generic) [Supported]
✓ 2. Package Managers: Available: APT, FLATPAK, SNAP, APPIMAGE
✓ 3. Repository Health: 24 active sources across 6 files
✓ 4. /boot Partition & Kernel Health: 480 MB free (48.0%), 3 kernels installed (Booted: 6.8.0-49-generic)
✓ 5. Database Storage: ~/.local/share/ulum/ulum.db (Schema v2, 64.0 KB, Integrity: OK)
✓ 6. Package Manager Locks: No active or stale package manager locks detected
✓ 7. Inventory & Scan Freshness: Inventory scan completed 0.4 hours ago
✓ 8. ULUM Version & Updates: v0.4.0 (Up to date)

✓ All diagnostic checks passed (System Healthy).
```

---

## 💻 CLI Reference

| Command | Description |
| :--- | :--- |
| `ulum doctor [--fix] [--fix-repos] [--restore-repos] [--json]` | Diagnose system health across the 8-point checklist (repairs stale locks/dpkg, disables broken 404 PPAs, restores backups, or outputs structured JSON). |
| `ulum scan` | Index all installed packages across APT, Flatpak, Snap, and AppImage into local inventory. |
| `ulum check [--refresh]` | Query available updates across all active package managers with estimated download sizes. |
| `ulum list [--updates]` | Display installed applications or pending updates in rich tables. |
| `ulum info <id>` | Inspect metadata for a package (e.g. `apt:curl` or `flatpak:org.mozilla.firefox`). |
| `ulum update --all` | Update all eligible packages across all sources with bandwidth/metered safety checks. |
| `ulum update --security-only` | Update only packages tagged as Security or Critical (APT-only in v0.4). |
| `ulum update <id>` | Update a specific application through its native manager. |
| `ulum update --dry-run` | Preview proposed updates without modifying the system. |
| `ulum schedule [--install]` | Configure systemd automated background update checks and desktop notifications. |
| `ulum integrate [path] [--all] [--remove <id>]` | Register standalone AppImages into desktop application menu or cleanly unintegrate/remove existing launchers. |
| `ulum remove <id>` | Perform standard native uninstallation. |
| `ulum remove <id> --complete` | Complete removal (purge configs and verified application data). |
| `ulum leftovers` | Discover orphaned residual configuration and data directories. |
| `ulum cleanup [--yes]` | Review and permanently delete verified residual leftovers. |
| `ulum cleanup --kernels [--yes]` | Purge obsolete Linux kernels and free `/boot` partition space while protecting running and fallback kernels. |
| `ulum self-update [--check]` | Check for newer ULUM releases on GitHub and perform automated in-place upgrades. |
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

- **Home (Bento Dashboard)**: Live 0-100 Health Score with itemized deduction breakdowns, updates count by urgency (Security, Critical, Feature, Unknown) with "Security tagging is APT-only in v0.4" notice, 1-click "Update Security Only", `/boot` partition storage monitor, repository health, and recent operations history.
- **Live Updates Tab**: View pending updates across all sources, filter by urgency, see total estimated download sizes (with amber warnings if > 1 GB), and update security-only, individually, or in bulk.
- **Installed Software Tab**: Search, filter by source, inspect dependencies, trigger standard and complete uninstalls, and 1-click **Integrate AppImages** into your desktop menu.
- **Leftovers & Cleanup Tab**: Browse residual directories with confidence ratings and 1-click **Clean Old Kernels** to free `/boot` space.
- **Diagnostics Tab (System Doctor)**: Interactive live 8-point checklist view with 1-click **Fix 404 Repos**, **Restore Repo Backups**, and **Repair Stale Locks**.
- **Operation History Tab**: Track past system operations (updates, removals, repo fixes, kernel cleans, integrations, self-updates), exit codes, and timestamps.
- **Settings Tab**: View environment details, configure package managers, and use the **ULUM Application Updates** card to check GitHub releases, verify SHA256 checksums, and manage rollback binaries.

> [!NOTE]
> When launched from the application launcher or via `ulum-gui`, ULUM uses PolicyKit (`pkexec`) to prompt for administrative authorization once. The dashboard runs in **Root Administrator** mode with X11 display access forwarding, enabling seamless in-app package downloads and installations while preserving the user's database inventory.

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
tests/integration/test_cli.py ......
tests/unit/test_adapters.py .......
tests/unit/test_db.py ........
tests/unit/test_doctor.py ..........
tests/unit/test_executor.py ......
tests/unit/test_gui.py ..
tests/unit/test_leftovers.py ...
tests/unit/test_new_features.py ...............
tests/unit/test_planner.py ...
tests/unit/test_safety.py .....
tests/unit/test_server.py .
tests/unit/test_system_and_config.py ...

============================== 69 passed ==============================
```

---

## 👨‍💻 Author

Designed and built by **[Abdurrahman](https://github.com/Akai-Abd)**.

---

## 📄 License

Distributed under the [MIT License](LICENSE). Built with Python, Typer, Rich, GTK3, and WebKit2.
