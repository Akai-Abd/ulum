# Changelog

All notable changes to the **ULUM (Universal Linux Update Manager)** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.1] - 2026-11-23

### 🎨 GTK3 Dashboard Visual Overhaul & Interactive Navigation

- **Lightweight CSS Provider & Modern Card Styling (`_init_styles`)**:
  - Injected theme-respecting CSS provider with `.dashboard-card` container styles using GTK theme palette variables (`@theme_bg_color`, `@borders`), providing rounded corners (`border-radius: 8px`), subtle contrast backgrounds, and clean padding without third-party themes.
  - Seamlessly adapts to host dark and light themes across GNOME, Linux Mint (Cinnamon), XFCE, and KDE Plasma.
- **Hero Health Score Widget & Native `Gtk.LevelBar`**:
  - Replaced plain text health score label with prominent hero typography (`<span size='24000'>`) and quantitative status chip badges (`Optimal`, `Attention Needed`, `Critical`).
  - Added native `Gtk.LevelBar` displaying dynamic level offsets (Green > 85, Yellow 60–84, Red < 60) for instant health evaluation at a glance.
- **Interactive Urgency Metric Pills**:
  - Replaced static text summary with clickable pill badges (`🛡️ Security`, `⚠️ Critical`, `✨ Feature`, `📦 Other`) on the Home dashboard.
  - Clicking any urgency pill immediately jumps to the **Updates** tab (`_filter_updates_to`) and automatically activates that urgency filter in the list.
- **Visual `/boot` Storage Gauge (`Gtk.ProgressBar`)**:
  - Added visual progress bar showing exact megabytes used vs. total capacity (`MB / MB used (%) — MB free`).
  - Automatically highlights the "Clean Old Kernels" button with `.destructive-action` when `/boot` free space drops below the 100 MB critical threshold.
- **Dedicated Urgency Filtering in Updates View**:
  - Added an urgency dropdown filter (`Gtk.ComboBoxText`) connected to `Gtk.TreeModelFilter` in the Updates toolbar.
- **In-App Manual Upgrade Button**:
  - Added dedicated "Upgrade Application" / "Upgrade to vX.X.X" button in the Settings view (`self.btn_upgrade_self`).
  - Automatically enables and highlights with `suggested-action` styling when a newer release is discovered on GitHub.
  - Automatically prompts for immediate upgrade confirmation when checking releases, executing background package download, SHA256 checksum verification, and reinstall via `SelfUpdater.apply_update`.
- **FreeDesktop Symbolic System Icons**:
  - Added standard symbolic desktop icons across all 7 notebook view tabs (`go-home-symbolic`, `software-update-available-symbolic`, `system-software-install-symbolic`, `user-trash-symbolic`, `dialog-information-symbolic`, `document-open-recent-symbolic`, `emblem-system-symbolic`), card titles, and header buttons.

### 🐞 Fixes & Reliability

- **Dynamic Versioning & SelfUpdater Sync**:
  - Replaced hardcoded version strings in `SystemDoctor.check_version_and_updates` and GUI Settings with dynamic package version `__version__`.
  - Fixed candidate query to call `Repository.get_cleanup_candidates()` on the Home dashboard.
  - Fixed `test_cli_doctor` test assertion to match case-normalized diagnostic outputs.
  - Maintained 100% test suite pass rate (69/69 passed).

---

## [0.4.0] - 2026-11-23

### 🖥️ Native Desktop GUI Modernization (v0.4.0 Step 5)

- **Native GTK Desktop Application (`src/ulum/gui/window.py`)**:
  - Replaced the embedded WebKit2 browser and local HTTP server architecture with an instant, native GTK desktop interface, removing browser engine startup overhead and eliminating X11/DMABUF driver instability.
  - Implemented 7 structured views matching PRD §6.4: Home (Bento Dashboard), Updates, Installed Software, Leftovers & Cleanup, Diagnostics (Doctor), History, and Settings & About.
  - Added lightweight GTK CSS provider injecting `.dashboard-card` visuals using system theme colors (`@theme_bg_color`, `@theme_fg_color`, `@borders`) ensuring seamless dark and light mode blending across Linux Mint, GNOME, XFCE, and KDE.
  - Integrated FreeDesktop symbolic icons across card headers, action buttons, and notebook view tab labels without extra asset files.
- **Bento Home Dashboard & Transparent Health Score Engine (`calculate_health_score`)**:
  - Quantitative 0-100 Health Score starting at 100 with itemized, visible deductions per PRD §6.3:
    - Pending Security updates (-5 pts each, max -30)
    - Pending Critical updates (-4 pts each, max -20)
    - Repository health issues and 404 dead PPAs (-10 to -20 pts)
    - `/boot` partition storage pressure (-10 pts)
    - Stale package manager locks (-10 pts)
    - Unscanned inventory older than 24h (-10 pts)
    - Verified cleanup leftovers exceeding 1 GB (-5 pts)
  - Hero Health Score widget displaying large typography, prominent status badge (`Optimal`, `Attention Needed`, `Critical`), and a native `Gtk.LevelBar` with green (>85), yellow (60-84), and red (<60) offsets.
  - Interactive urgency metric pills (`🛡️ Security`, `⚠️ Critical`, `✨ Feature`, `📦 Other`) providing 1-click jump and automated filtering in the Updates view.
  - Dedicated urgency filter dropdown in the Updates view (`Gtk.TreeModelFilter`).
  - Visual `/boot` partition storage gauge (`Gtk.ProgressBar`) showing consumed vs. total capacity and highlighting kernel cleanup with `.destructive-action` when free space < 100 MB.
  - 1-click quick action buttons: "Update Security Only", "Clean Old Kernels", "Fix 404 Repos", and "Review Leftovers".
- **Integrated Diagnostics & Settings**:
  - Live 8-point checklist view in the Diagnostics tab with 1-click PPA repair, repo backup restoration, and stale lock clearing.
  - Self-updater control card in Settings with release notes inspection and rollback execution.

### 🩺 Unified Health Doctor CLI & Health Model v2 (v0.4.0 Step 4)

- **Comprehensive 8-Point Health Checklist (`src/ulum/doctor/health.py`)**:
  - Implemented `SystemDoctor` executing the complete PRD §12 diagnostic checklist in strict sequence:
    1. Distribution, kernel, and architecture detection with supported platform verification.
    2. Package manager availability (APT, Flatpak, Snap, AppImage).
    3. Repository health (active source counting, syntax validation, and disabled entry tracking).
    4. `/boot` storage health and kernel counting (critical alert if < 100 MB, warning if < 250 MB).
    5. Database integrity, schema version (v2 migration status), and storage access.
    6. Package manager lock inspection (`/var/lib/dpkg/lock-frontend`, `/var/lib/apt/lists/lock`, etc.) checking active holding processes vs. defunct/dead PIDs.
    7. Inventory scan freshness (warns if scan is older than 24 hours or uninitialized).
    8. ULUM version and online self-update check.
- **Machine-Readable JSON Diagnostics (`ulum doctor --json`)**:
  - Emits clean, parseable JSON containing all 8 check details, timestamps, overall status (`healthy`, `degraded`, `failed`), failing checks list, and exit code.
  - Returns standard exit codes: Exit 0 for healthy or degraded (warnings), Exit 1 for failed checks, Exit 2 for fatal/missing input.
- **Automated Stale Lock Repair (`ulum doctor --fix`)**:
  - Safely discovers and removes stale lock files where the holding PID is defunct/dead without disturbing actively running package manager processes.
  - Triggers `dpkg --configure -a` and `apt-get install -f -y` to repair interrupted package states.

### 🛡️ P0 Safety Hardening for Carried-Forward Modules (v0.4.0 Step 3)

- **AptRepoDoctor Automatic Backups & Restoration (`src/ulum/doctor/repos.py`)**:
  - Automatically creates a timestamped pre-modification backup file (`<path>.ulum-backup-<timestamp>`) before modifying any APT repo or sources file.
  - Enforces strict target path allow-listing: edits are restricted to verified sources list files under `/etc/apt/sources.list` or `/etc/apt/sources.list.d/`.
  - Added `restore_all_backups()` and corresponding CLI flag `ulum doctor --restore-repos` to restore all modified repo configurations from their latest backups in one operation.
- **KernelCleaner Safety & Boot Integrity Guards (`src/ulum/removal/kernels.py`)**:
  - Running Kernel Guard: Inspects `uname -r` and strictly refuses deletion of any package matching the running kernel.
  - 2-Kernel Minimum Rule: Aborts kernel purges if the cleanup plan leaves fewer than 2 installed kernels (active running kernel + newest fallback kernel).
  - Third-Party Driver Safety: Detects compiled DKMS modules in `/var/lib/dkms` and warns users of potential driver recompilation/breakage before purging headers.
  - Snapshot Protection: Detects Timeshift and Snapper (`detect_snapshot_tool()`) and prompts/logs pre-cleanup system snapshot recommendations.
  - Emergency Recovery Guidance: Emits explicit recovery instructions ("Do NOT reboot until fixed: run `sudo apt --fix-broken install`") upon any partial or failed kernel purge.
- **SelfUpdater Cryptographic Verification & Rollback (`src/ulum/utils/self_update.py`)**:
  - Mandatory SHA256 checksum verification (`apply_update(expected_sha256=...)`) before applying or installing release binaries/packages.
  - Rollback Preservation: Preserves previous running executable in `~/.local/share/ulum/rollback/` prior to binary replacement.
  - Post-Install Launch Verification: Performs a smoke test (`ulum --version`) following installation; rolls back automatically if verification fails.
- **AppImage Integration Collision Protection & Unintegration (`src/ulum/adapters/appimage.py`)**:
  - Collision Detection: Backs up existing `.desktop` files (`.desktop.backup`) before overwriting during desktop registration.
  - Strict Path Validation: Enforces that target files exist and possess the `.AppImage` extension.
  - Unintegration Support: Implemented `unintegrate_appimage()` and `ulum integrate --remove <id>` to cleanly deregister desktop entries and restore original backups.

### ⚡ Parallel Async Engine & Security Tagging (v0.4.0 Step 2)

- **Concurrent Async Scanner (`src/ulum/core/orchestrator.py`)**:
  - Refactored `scan_all()` and `check_updates()` to execute package manager checks concurrently across APT, Flatpak, Snap, and AppImage via `asyncio.to_thread` and `asyncio.gather`.
  - Added strict 30-second per-adapter timeouts preventing slow or stalled remotes (e.g. unreachable Flatpak hubs) from holding up system scans.
  - Failures and timeouts report with their exact error message and elapsed time; broken adapters are never silently reported as 0 updates.
  - Implemented 1-hour inventory cache TTL with age reporting in CLI and GUI.
- **APT Security Origin Tagging (`src/ulum/adapters/apt.py`)**:
  - Implemented `parse_apt_upgradable_line()` parsing the origin pocket in `apt list --upgradable`.
  - Upgrades arriving from pockets ending with `-security` (e.g. `noble-security`) are automatically tagged `urgency="Security"`; non-security updates remain `"Unknown"`.
- **Security-First CLI (`ulum update --security-only`)**:
  - Added `--security-only` flag to `ulum update`, `ulum check`, and `ulum list --updates`.
  - Filters update targets strictly to Security and Critical candidates, ensuring users can patch critical vulnerabilities without performing full distribution upgrades.
  - Displays "Urgency" badge column in the CLI Available Updates table.

### 🗄️ Database Schema & Data Model Modernization (v0.4.0 Step 1)

- **Versioned SQLite Schema Migrations (`src/ulum/db/migrations.py`)**:
  - Implemented versioned migration framework using SQLite `PRAGMA user_version` (Version 2 / v0.4.0).
  - Automatically migrates existing v0.3.0 databases without data loss or manual user intervention.
- **Security Urgency Tracking on Pending Updates**:
  - Added `urgency` column (`Security`, `Critical`, `Feature`, `Optional`, `Unknown`) to the `updates` table with default value `'Unknown'`.
  - Added `UrgencyLevel` enum and `is_security_only()` predicate in `src/ulum/core/models.py`.
- **Dedicated Audit & Operation Tracking Tables**:
  - `operation_history`: Unified log tracking all operations (`update`, `remove`, `repo_fix`, `kernel_clean`, `integrate`, `self_update`, `snapshot`) with status, exit code, plan summary, backup path, snapshot ID, and timings.
  - `repo_fixes`: Detailed logging for AptRepoDoctor repository repairs, lines commented, and backup paths.
  - `kernel_cleans`: Obsolete kernel purge history, packages removed, space freed, and snapshot status.
  - `appimage_integrations`: Standalone AppImage desktop launcher registrations, backups, and status.
  - `download_estimates`: Bandwidth estimation caching per source with expiration timestamps.
  - `self_updates`: ULUM self-update log with SHA256 verification status and rollback artifact paths.
- **Repository Methods**:
  - Extended `Repository` in `src/ulum/db/repository.py` to record and query operation history, repo fixes, kernel cleans, and self-updates.
  - Updated `save_updates` and `get_updates` to store and retrieve update urgency levels.

---

## [0.3.0] - 2026-11-21

### 🚀 Major Feature Release: System Health, /boot Protection, AppImage Integration & In-App Self-Updates

- **🏥 Broken PPA & 404 Repository Auto-Repair (`ulum doctor --fix-repos` / GUI)**:
  - Added automated detection of dead, expired, or 404 repositories in `/etc/apt/sources.list` and `/etc/apt/sources.list.d/*.list` / `*.sources`.
  - Implemented safe in-place commenting of failing source lines (`# DISABLED BY ULUM (404/broken): ...`), restoring standard `apt-get update` functionality without manual terminal editing.
  - Added "Fix 404 Repos" action button in the GUI Diagnostics view and `--fix-repos` flag to the `ulum doctor` CLI command.

- **🧹 Obsolete Linux Kernel & `/boot` Partition Saver (`ulum cleanup --kernels` / GUI)**:
  - Added intelligent kernel cleanup that safeguards the active booted kernel (`uname -r`) and the newest fallback kernel, while safely identifying older orphaned kernels and residual `config-files`.
  - Accurately computes disk space savings across image, module, and header packages.
  - Implemented strict safety guards refusing deletion of any package matching the running kernel.
  - Added "Clean Old Kernels" action in the GUI Leftovers/Cleanup view and `--kernels` (`-k`) flag to the `ulum cleanup` CLI command.

- **📦 Standalone AppImage Desktop Integrator (`ulum integrate` / GUI)**:
  - Added automatic XDG desktop launcher generation in `~/.local/share/applications/*.desktop` for standalone AppImages discovered in `~/Downloads`, `~/Applications`, and `~/.local/bin`.
  - Automatically ensures executable permissions (`chmod +x`), generates clean `.desktop` metadata, and calls `update-desktop-database` to immediately display AppImages in desktop start menus and application launchers.
  - Added "Integrate AppImages" action button in the GUI Installed Applications view and new `ulum integrate` CLI command.

- **📶 Download Size Estimator & Metered Connection Warning (`ulum check` / `ulum update` / GUI)**:
  - Added pre-upgrade download size calculation for APT (`apt-get -s dist-upgrade`) and Flatpak (`flatpak remote-ls --columns=download-size`).
  - Added automatic metered connection warning badge (`⚠️ Large Download (> 1 GB)`) in the desktop dashboard and confirmation dialogs before initiating bulk updates.
  - Displays download breakdown and warnings in CLI `ulum check` and `ulum update`.

- **🔄 In-App Self-Update Checker in Settings Dashboard (`ulum self-update` / GUI)**:
  - Added dedicated "ULUM Application Updates" card in the GUI Settings Dashboard with a "Check for Updates" button (`#btn-check-app-update`).
  - Queries GitHub Releases API with automated version comparison and changelog preview.
  - Provides a one-click "Upgrade Now" action that downloads the latest `.deb` package and upgrades ULUM directly in-app.
  - Added `ulum self-update` and `ulum self-update --check` CLI commands.

---

## [0.2.2] - 2026-11-20

### 🛡️ Production Hardening & Full Audit Remediation

- **🔒 Security & Remote Access Hardening**:
  - Eliminated remote cross-origin access and CSRF attack vectors on the local GUI server by removing the CORS wildcard (`*`), rejecting non-local Origin headers with HTTP 403, and requiring session authentication tokens (`X-ULUM-Token`) on all mutating endpoints.
  - Remediated stored Cross-Site Scripting (XSS) in the WebKit dashboard by replacing raw HTML string interpolations and inline `onclick` attributes with secure DOM element creation and event listeners.

- **🐞 Core Reliability & Safety**:
  - Fixed silent uninstallation failure on AppImages lacking cached locations by dynamically updating the application record with the resolved binary path and reading fallback targets from native commands.
  - Fixed case-sensitivity mismatch in `RemovalPlanner` to correctly identify critical system directory warnings and flag dangerous removal plans as unsafe.
  - Ensured thread-safe SQLite operations by protecting all repository queries and transactions with a re-entrant lock (`threading.RLock`), preventing cursor collisions across multi-threaded web server requests.
  - Hardened automated APT updates with non-interactive flags (`DEBIAN_FRONTEND=noninteractive`, `--force-confdef`, `--force-confold`) to prevent indefinite hangs on configuration-file conflict prompts.
  - Corrected APT reverse-dependency analysis to flag package removals as unsafe whenever installed packages depend on the target.
  - Added snapshot pre-check failure gating so update operations abort safely if requested Timeshift or Snapper restore points fail to create.

- **🧹 Residual Scanner Precision & Atomic Persistence**:
  - Refined leftover scanner prefix matching with strict word boundary delimiters (`-`, `_`), preventing installed utilities (e.g., `git`, `ed`, `code`) from falsely suppressing uninstalled application cleanup detection.
  - Implemented atomic crash-safe file writes with temporary files and `fsync` for `config.toml` persistence.
  - Synchronized pending updates state upon successful upgrades, immediately clearing installed packages from the pending queue.
  - Replaced row-by-row insertion loops in `save_updates` and `save_cleanup_candidates` with high-throughput batch `executemany` operations.
  - Deduplicated directory size calculations during removal planning.

- **🖥️ Desktop & CLI Usability**:
  - Added AppImage support to the native GTK fallback window's source filter.
  - Added platform guards to `ulum doctor --fix` to verify Debian/APT binary availability before attempting recovery.

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
