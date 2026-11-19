# Changelog

All notable changes to the **ULUM (Universal Linux Update Manager)** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
