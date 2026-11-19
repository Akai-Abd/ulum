# Changelog

All notable changes to the **ULUM (Universal Linux Update Manager)** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.1] - 2026-11-20

### 🛡️ Quality Audit & Performance Fixes

- **Database Performance & Safe Pruning**:
  - Replaced individual row insertion loops in `save_applications` with high-throughput batch `executemany` operations.
  - Eliminated parameter overflow risk (`too many SQL variables`) on large APT inventories by replacing unbounded `DELETE ... NOT IN (?, ?, ...)` queries with single-query timestamp pruning (`DELETE ... WHERE source = ? AND last_scanned_at < ?`).

- **Residual Scanner Accuracy & Desktop Safeguards**:
  - Broadened generic desktop system protection list to prevent false leftover detection in user environments (`cinnamon`, `gnome-session`, `thumbnails`, `pip`, `mesa_shader_cache`, `evolution`, `nemo`, `nautilus`, etc.).
  - Added prefix and substring matching against installed package IDs so active applications whose directory names differ slightly (e.g., `google-chrome` for `google-chrome-stable`, `libreoffice` for `libreoffice-core`) are not falsely flagged as leftovers.

- **GUI Settings Persistence**:
  - Added the AppImage toggle (`cfg-appimage`) to the desktop GUI settings panel, configuration state loader, and save handler, preventing AppImage support from being silently disabled when settings were saved from the WebKit dashboard.

- **CLI Schedule Usability**:
  - Changed default invocation of `ulum schedule` to safely query and display the active timer status instead of immediately writing systemd service and timer units without confirmation flags.

- **AppImage Discovery & Removal Robustness**:
  - Added permission and file error handling (`OSError`, `PermissionError`) when inspecting search directories.
  - Added fallback search path resolution in `build_removal_plan` when an application lacks a cached install location.
  - Included `~/.config/{package_id}` in complete removal plans for AppImages.

- **Safety Validator Hardening**:
  - Strengthened system directory blacklist validation to check child paths and parent containment against protected OS paths.

---

## [0.2.0] - 2026-11-20

### 🚀 Enhancements & New Capabilities

- **AppImage & Standalone Binary Tracking**:
  - Added dedicated `AppImageAdapter` scanning `~/Applications`, `~/.local/bin`, and custom `.desktop` files in `~/.local/share/applications/`.
  - Supports tracking version, binary paths, desktop integration, and clean uninstallation (unlinking binary and removing desktop launcher).
  - Integrated into core orchestrator and enabled by default in configuration.

- **Pre-Update System Snapshots (Timeshift & Snapper)**:
  - Added system restore snapshot hooks prior to applying system updates.
  - Automatically detects Timeshift (`timeshift --create`) or Snapper (`snapper create`) with non-interactive root escalation.
  - New `--snapshot` / `-S` flag for `ulum update` CLI command.
  - Desktop GUI update confirmation modal now includes a toggle to create a pre-update snapshot.

- **System Health Diagnostics & Automated Repair**:
  - Enhanced `ulum doctor` with an automated repair routine (`ulum doctor --fix` / `-f`).
  - Clears stale APT locks and fixes interrupted dpkg states (`dpkg --configure -a` and `apt-get install -f -y`).

- **Automated Update Checks & Desktop Notifications**:
  - New `ulum schedule` command managing systemd user services (`ulum-check.service` and `ulum-check.timer`).
  - Periodically checks for updates in the background and delivers native desktop notifications via `notify-send`.
  - Provides `--install`, `--uninstall`, and `--status` flags.

- **Non-blocking Desktop GUI Concurrency**:
  - Converted internal GUI HTTP server to `ThreadedTCPServer` with thread-safe tracking of current operations (`CURRENT_OPERATION`).
  - Introduced `/api/progress` endpoint so long-running operations (such as system updates or snapshots) never block the UI thread.
  - Added snapshot checkbox to desktop GUI update modal.

- **Residual Scanner Refinement**:
  - Expanded leftover directory discovery in `~/.config` and `~/.cache` to match dotless folder patterns.
  - Added generic desktop folder protection list (`dconf`, `gtk-3.0`, `pulse`, `systemd`, `mime`, etc.) to prevent accidental removal of shared environment configurations.
  - Guarded Flatpak and Snap removal item generation to prevent false data loss warnings during standard uninstalls.

- **Native Debian Packaging & CI/CD**:
  - Added `scripts/build_deb.sh` to package ULUM directly into standard Debian `.deb` packages with binary launchers and `.desktop` integration.
  - Added GitHub Actions release workflow (`.github/workflows/release.yml`) for automated testing and `.deb` asset generation on tagged releases.

---

## [0.1.0] - 2026-11-20

### 🌟 Initial Release Highlights

Welcome to the initial release of **ULUM (Universal Linux Update Manager)** — a package management coordinator and safe uninstaller for Linux that unifies APT, Flatpak, and Snap into one CLI and desktop GUI.

### ✨ Features & Capabilities

- **Unified Package Management**:
  - Multi-source scanning and indexing across system packages (**APT**), sandboxed runtimes (**Flatpak**), and containerized applications (**Snap**).
  - Bulk and selective update checking (`ulum check`) and execution (`ulum update`).
  - Native dependency and reverse-dependency inspection (`ulum dependencies`).

- **Safe Uninstallation & Residual Cleanup**:
  - Dual uninstallation modes: standard native removal and complete uninstallation (`--complete` / purge config & data).
  - Residual leftover scanner detecting orphaned user directories in `~/.var/app`, `~/snap`, `~/.config`, and `~/.cache`.
  - Dry-run simulation mode (`--dry-run`) across updates and removals to preview exact native commands and freed disk space.

- **Desktop Graphical Interface**:
  - Dark-mode glassmorphic dashboard built on GTK3 and embedded WebKit2 (with automatic fallback to native GTK controls).
  - Real-time updates tab with one-click individual or bulk upgrades.
  - Installed applications browser with instant search, source filtering, and dependency viewer.
  - Leftover manager with size breakdown and single-click or batch removal.
  - Settings panel to toggle package managers, exclude packages, and control confirmation dialogs.

- **Storage & Diagnostics**:
  - Embedded WAL-mode SQLite database tracking applications, updates, and operation history.
  - Built-in system health diagnostics (`ulum doctor`) for platform, manager availability, and permissions.

### 🛡️ Safety Safeguards

- Hardened path validation rejecting critical system directories (`/`, `/bin`, `/boot`, `/etc`, `/usr`, `/var`, etc.).
- Protected user paths shielding personal files (`~/Documents`, `~/Downloads`, `.bashrc`, etc.).
- Containment validation preventing symlink directory traversal attacks outside allowed cleanup bases.
- Verification of orphan directories against active native managers before marking as cleanup candidates.

### 🧪 Test Suite

- Comprehensive test suite with 28 unit and integration tests covering CLI commands, adapters, database repository, safety validators, execution planner, and the local GUI API server.
