# 🐧 ULUM — Universal Linux Update Manager

<div align="center">

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Linux%20(Mint%20%7C%20Ubuntu)-orange.svg?style=flat-square&logo=linux)](https://github.com/Akai-Abd/ulum)
[![Package Managers](https://img.shields.io/badge/sources-APT%20%7C%20Flatpak%20%7C%20Snap%20%7C%20AppImage-success.svg?style=flat-square)](https://github.com/Akai-Abd/ulum)
[![GUI](https://img.shields.io/badge/GUI-GTK3%20%2B%20WebKit2%20Dashboard-purple.svg?style=flat-square)](https://github.com/Akai-Abd/ulum)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Built by](https://img.shields.io/badge/Built%20by-Abdurrahman-7c3aed.svg?style=flat-square&logo=github)](https://github.com/Akai-Abd)

**An intelligent, multi-source package manager and safe uninstaller for Linux.**  
Seamlessly orchestrate software updates and clean removals across **APT**, **Flatpak**, **Snap**, and **AppImage** from a unified CLI and modern glassmorphic desktop GUI.

[Features](#-key-features) • [Quickstart](#-quickstart) • [CLI Reference](#-cli-reference) • [GUI Dashboard](#-desktop-gui) • [Safety Architecture](#-safety--residual-protection) • [Contributing](#-development)

---

</div>

## 🌟 Key Features

- **Unified Multi-Source Updates**: Check and upgrade packages across system repositories (APT), sandboxed runtimes (Flatpak), containerized snaps (Snap), and standalone binaries (AppImage) in one command.
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
- **Modern Glassmorphic Desktop GUI**: Dark-mode glassmorphic dashboard built with GTK3 and embedded WebKit2 backed by a threaded asynchronous server.
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
- GTK3 and WebKit2 (`gir1.2-webkit2-4.1` for desktop GUI)

### 1. Installation

#### Option A: Debian Package (.deb) — Recommended

Install the pre-built `.deb` package directly:

```bash
sudo dpkg -i ulum_0.3.0_all.deb
# Or from the repository root:
sudo dpkg -i dist/ulum_0.3.0_all.deb
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
| `ulum doctor [--fix] [--fix-repos]` | Diagnose distro compatibility, package managers, and storage health (auto-repairs dpkg/locks or disables broken 404 PPAs). |
| `ulum scan` | Index all installed packages across APT, Flatpak, Snap, and AppImage into local inventory. |
| `ulum check [--refresh]` | Query available updates across all active package managers with estimated download sizes. |
| `ulum list [--updates]` | Display installed applications or pending updates in rich tables. |
| `ulum info <id>` | Inspect metadata for a package (e.g. `apt:curl` or `flatpak:org.mozilla.firefox`). |
| `ulum update --all` | Update all eligible packages across all sources with bandwidth/metered safety checks. |
| `ulum update <id>` | Update a specific application through its native manager. |
| `ulum update --dry-run` | Preview proposed updates without modifying the system. |
| `ulum schedule [--install]` | Configure systemd automated background update checks and desktop notifications. |
| `ulum integrate [path] [--all]` | Register standalone AppImages into desktop application menu and application launcher. |
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

- **Live Updates Tab**: View pending updates across all sources, see total estimated download sizes (with amber warnings if > 1 GB), and update individually or in bulk.
- **Installed Software Tab**: Search, filter by source, inspect dependencies, trigger standard and complete uninstalls, and 1-click **Integrate AppImages** into your desktop menu.
- **Leftovers & Cleanup Tab**: Browse residual directories with confidence ratings and 1-click **Clean Old Kernels** to free `/boot` space.
- **Diagnostics Popover**: View package manager health and 1-click **Fix 404 Repos** to safely comment out dead PPAs.
- **Operation History Tab**: Track past system operations, exit codes, and timestamps.
- **Settings Tab**: Toggle package managers, exclude packages from auto-updates, configure confirmation prompts, and use the **ULUM Application Updates** card to check GitHub and upgrade ULUM directly in-app.

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
tests/integration/test_cli.py .....
tests/unit/test_adapters.py ......
tests/unit/test_db.py ........
tests/unit/test_executor.py ...
tests/unit/test_gui.py .
tests/unit/test_leftovers.py ...
tests/unit/test_new_features.py .........
tests/unit/test_planner.py ...
tests/unit/test_safety.py .....
tests/unit/test_server.py .
tests/unit/test_system_and_config.py ...

============================== 47 passed ==============================
```

---

## 👨‍💻 Author

Designed and built by **[Abdurrahman](https://github.com/Akai-Abd)**.

---

## 📄 License

Distributed under the [MIT License](LICENSE). Built with Python, Typer, Rich, GTK3, and WebKit2.
