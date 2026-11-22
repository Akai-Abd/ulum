# Product Requirements Document (PRD)
# Universal Linux Update Manager (ULUM)

**Document version:** 0.4.0  
**Status:** Complete (v0.4.0 Implemented & Verified)  
**Product type:** Open-source Linux CLI utility and Modern Native GTK Desktop GUI  
**Initial target platforms:** Linux Mint 22.x and Ubuntu 24.04 LTS  
**Primary implementation language:** Python 3.12+  
**Proposed command:** `ulum` (CLI) / `ulum-gui` (GUI)

---

## 1. Executive summary

Universal Linux Update Manager (ULUM) is a Linux-first command-line application that provides one consistent interface for discovering installed software, checking for updates, updating applications, uninstalling applications, and reviewing verified leftover files.

Linux software is distributed through several independent ecosystems, including APT/DEB, Flatpak, Snap, AppImage, and application-specific installers. Each ecosystem has its own inventory, update, removal, permission, and data-retention behavior. ULUM will coordinate these native mechanisms through a modular adapter architecture rather than replacing package managers or attempting to manage their databases directly.

The product has two core capabilities:

1. **Update management:** discover supported applications, check for updates, preview changes, and execute user-approved updates.
2. **Application removal and cleanup:** uninstall applications through their original installation mechanism, analyze dependencies and residual files, and remove only items that are verified and explicitly approved.

ULUM must be honest about its limits. There is no reliable universal method to update or completely remove every arbitrary Linux application. AppImages, manually installed binaries, vendor installers, and custom scripts require identifiable metadata, manifests, or application-specific integrations. Unknown files must never be deleted merely because their names resemble an application name.

## 2. Problem statement

Linux users may install software through multiple package managers and manual installation methods. This creates several practical problems:

- Users must run different commands to inspect and update different software sources.
- Installed applications and available updates are spread across independent package ecosystems.
- Some applications do not provide update metadata through a system package manager.
- AppImages and manually installed applications may have no standard update or uninstall mechanism.
- Removing a package does not necessarily remove user data, caches, or application-specific configuration.
- Dependency cleanup can be risky when packages or libraries are shared.
- Users lack one consistent place to review update and removal history.

**Proposed solution:** provide one CLI and optional TUI that discovers supported software sources, delegates operations to their native tools, previews potentially destructive actions, and records the results.

## 3. Product goals

1. Detect the operating system, version, architecture, and available package managers.
2. Build a useful inventory of installed applications from supported sources.
3. Check and report available updates using each source's native mechanism.
4. Update one application, one source, or all supported applications.
5. Uninstall applications using the mechanism that owns their installation.
6. Offer standard, complete, and custom cleanup workflows with explicit safeguards.
7. Identify dependencies, application data, configuration, caches, and potential leftovers.
8. Preview operations before execution and require confirmation for destructive actions.
9. Maintain update and removal history with useful diagnostic information.
10. Support additional distributions and adapters without redesigning the core.

## 4. Non-goals

The initial product will not:

- Replace APT, Flatpak, Snap, or other native package managers.
- Directly edit package-manager databases.
- Guarantee updates for arbitrary binaries or software without update metadata.
- Guarantee complete removal of every trace of every application.
- Delete personal documents or user data by default.
- Automatically remove shared libraries or dependencies based only on name matching.
- Run arbitrary vendor scripts without explicit user configuration and review.
- Promise universal rollback; rollback depends on the package manager, filesystem, and available backups.
- Perform unattended system upgrades by default.

## 5. Target users and platforms

### 5.1 Target users

- Linux desktop users who install software from multiple sources.
- Linux Mint and Ubuntu users who want a centralized maintenance CLI.
- Developers and technical users who want inventory, diagnostics, and operation logs.
- Users who want to review application data and leftovers before uninstalling software.

### 5.2 Distribution support plan

| Distribution | Priority | Initial support expectation |
|---|---|---|
| Linux Mint 22.x | Primary | Full MVP testing |
| Ubuntu 24.04 LTS | Primary | Full MVP testing |
| Ubuntu 26.04 LTS | Later validation | Compatibility testing before claiming support |
| Debian 12/13 | Secondary | APT adapter validation |
| Fedora | Future | DNF adapter |
| Arch Linux | Future | Pacman adapter |
| openSUSE | Future | Zypper adapter |

ULUM must detect unsupported distributions and explain which features are unavailable. It must not assume that every Debian-derived distribution has identical package-manager behavior.

## 6. Supported installation sources and adapters

Each adapter must implement a documented interface for detection, inventory, update discovery, update execution, removal planning, removal execution, and verification where the source supports those operations.

### 6.1 APT / DEB — MVP

Capabilities:

- Detect APT availability and distribution details.
- Inventory installed packages and versions.
- Refresh repository metadata when requested.
- Check available package upgrades.
- Preview package changes where supported.
- Upgrade selected packages or all eligible packages.
- Remove packages and purge package-managed configuration.
- Identify automatically installed packages eligible for native autoremove analysis.
- Verify package state after operations.

Safety requirements:

- Use APT's dependency resolver; do not manually delete package files.
- Do not run broad `autoremove` as an invisible side effect of removing one application.
- Show packages proposed for removal before approval.
- Preserve package-manager locks and use native privilege handling.
- Distinguish package-owned configuration from user-level application data.

### 6.2 Flatpak — MVP

Capabilities:

- List installed Flatpak applications and runtimes.
- Identify installation scope (user or system), remote, application ID, branch, and version where available.
- Check and execute updates.
- Uninstall selected applications.
- Offer unused-runtime cleanup as a separately previewed action.
- Offer application data deletion only with explicit approval.

Safety requirements:

- Preserve the distinction between user and system installations.
- Do not assume an application ID is globally unique across installation scopes.
- Explain the effect of Flatpak's data-deletion options before using them.
- Preview unused runtimes and never remove a runtime still required by installed applications.

### 6.3 Snap — MVP

Capabilities:

- List installed snaps, versions, channels, and tracking information where available.
- Check refresh status using supported Snap interfaces.
- Refresh selected snaps or all eligible snaps.
- Remove selected snaps using Snap's native commands.
- Offer Snap data purge as an explicit destructive choice.
- Verify removal status.

Safety requirements:

- Delegate data and revision retention behavior to Snap.
- Explain that Snap may retain disabled revisions according to its own policies.
- Do not manually delete Snap-managed directories.

### 6.4 AppImage — Phase 2

Capabilities:

- Discover AppImage files in configured locations and known application directories.
- Record file path, file identity, size, modification time, and associated desktop entry where available.
- Detect update capability only when reliable update metadata or a supported updater is available.
- Integrate supported mechanisms such as AppImageUpdate when applicable.
- Remove the selected AppImage file and only verified, explicitly selected associated files.

Limitations:

- AppImage does not provide one universal update or uninstall protocol.
- A file's name or directory name is not sufficient proof of ownership.
- Do not remove shared data or user documents based on guessed associations.

### 6.5 Manually installed and vendor applications — Phase 3

Capabilities:

- Discover candidates in configured locations such as `/opt`, `~/.local/bin`, and user-selected directories.
- Track registered installation manifests.
- Support vendor-provided uninstallers or custom removal definitions only after user configuration and review.
- Support custom updater commands only when explicitly registered.

Limitations:

- Do not infer safe uninstall commands from executable names.
- Do not recursively delete `/opt`, `/usr/local`, home directories, or other broad paths.
- Do not overwrite or remove unknown binaries automatically.

### 6.6 Future adapters

Potential future adapters include DNF, Pacman, Zypper, Homebrew on Linux, language-specific package tools, and other distribution-specific systems. Each requires independent compatibility and safety testing before being marked supported.

## 7. Core product features

### 7.1 System detection and application inventory

ULUM should detect:

- Distribution ID, name, version, and base family.
- Kernel version and system architecture.
- Available package-manager executables and service status where relevant.
- Installed applications and package identifiers.
- Installation source and scope.
- Installed version and update status where available.
- Application installation path or manifest location where known.

Inventory records must preserve the original package identifier and source. Display names are not reliable unique identifiers.

### 7.2 Unified update checker

The checker should query each enabled adapter and present a consolidated report.

Example:

```text
Universal Linux Update Manager
System: Linux Mint 22.x

Sources detected: APT, Flatpak, Snap
Installed records: 185

Available updates:
  APT       12
  Flatpak    5
  Snap       2

Total update candidates: 19

Run `ulum update --dry-run` to preview changes.
```

Counts are illustrative. ULUM must report unavailable or failed sources separately rather than silently treating them as having zero updates.

### 7.3 Update execution

Users should be able to:

- Update a selected application.
- Update applications from one source.
- Update all supported applications.
- Exclude selected package identifiers.
- Preview proposed changes.
- Review package-manager output and exit status.
- Cancel operations when the underlying tool supports safe cancellation.

A bulk update must not imply distribution-release upgrades. System upgrades that change distribution versions are outside the MVP.

### 7.4 Application uninstaller and cleaner

The uninstaller is a core product capability.

It must identify the installation source and use the owning package manager or registered uninstall integration. It must create a removal plan before executing destructive actions.

Supported removal modes:

**Standard uninstall**
- Remove the selected application using its native mechanism.
- Preserve user configuration and application data unless the native source's behavior requires otherwise and the user is informed.
- Preserve shared dependencies.
- Do not run broad cleanup automatically.

**Complete uninstall**
- Perform the standard uninstall.
- Offer eligible unused dependency cleanup through the native package manager.
- Identify application-specific configuration, cache, logs, and data.
- Remove only verified application-owned files that the user has approved.
- Clearly list anything that cannot be safely attributed and leave it untouched.

**Custom cleanup**
- Allow the user to select cleanup categories individually.
- Show exact paths, ownership evidence, estimated size, and risk level.
- Require separate approval for personal data and broad or irreversible deletion.

“Complete” means the fullest safe cleanup ULUM can verify for that installation source. It is not a guarantee that every trace is removed.

### 7.5 Leftover discovery

The `leftovers` feature should identify candidates, not automatically delete them.

Potential evidence includes:

- Package-manager ownership records.
- Flatpak application ID and installation scope.
- Snap package identity and native data paths.
- AppImage registration or explicit user manifest.
- A custom installation manifest created or imported by the user.
- Known desktop entries and application-specific directories, when ownership is sufficiently established.

Each candidate must be classified:

- **Verified:** strong ownership evidence; eligible for a reviewed cleanup plan.
- **Probable:** naming or metadata suggests association but ownership is not conclusive; never auto-delete.
- **Unknown:** insufficient evidence; preserve.

### 7.6 History and diagnostics

Maintain separate update and removal histories, including:

- Application and package identifier.
- Installation source and scope.
- Previous and resulting versions, where available.
- Operation type and selected options.
- Start and finish timestamps.
- Success, failure, cancelled, or partial status.
- Exit code and sanitized diagnostic output.
- Files or dependencies removed, when reliably known.
- Data intentionally preserved.

Logs must avoid storing secrets, authentication tokens, or unnecessary personal file contents.

### 7.7 Notifications

Optional notifications:

- Updates available.
- Update completed or failed.
- Removal completed or partially completed.
- Cleanup candidates discovered.

Notifications must be opt-in or configurable and must not execute updates or removals by themselves.

### 7.8 Broken repository auto-repair (`AptRepoDoctor`)

- Automated detection of dead, expired, or 404 repositories in `/etc/apt/sources.list` and `/etc/apt/sources.list.d/*.list` / `*.sources`.
- In-place commenting of failing lines (`# DISABLED BY ULUM (404/broken): ...`), restoring `apt-get update` health without requiring manual terminal text editing.
- Exposed via CLI `ulum doctor --fix-repos` and 1-click "Fix 404 Repos" in the GUI Diagnostics view.

### 7.9 Obsolete Linux kernel & `/boot` partition cleanup (`KernelCleaner`)

- Detection and grouping of installed kernel packages (`linux-image-*`, `linux-headers-*`, `linux-modules-*`) by release.
- Strict safety model: preserves the active booted kernel (`uname -r`) and the latest fallback kernel.
- Safe purging of older orphaned kernels and residual `config-files` to recover hundreds of megabytes in `/boot`.
- Exposed via CLI `ulum cleanup --kernels` (supports `--dry-run`, `-y`) and 1-click "Clean Old Kernels" in the GUI Leftovers view.

### 7.10 Standalone AppImage desktop integration (`AppImageAdapter`)

- Auto-discovery of standalone `.AppImage` binaries across `~/Downloads`, `~/Applications`, and `~/.local/bin`.
- Auto-generation of clean XDG `.desktop` files in `~/.local/share/applications/` with executable bits (`chmod +x`).
- Automatic `update-desktop-database` trigger so AppImages appear immediately in the desktop application launcher.
- Exposed via CLI `ulum integrate [path] [--all]` and 1-click "Integrate AppImages" in the GUI Installed Applications view.

### 7.11 Pre-upgrade download size estimation & metered connection warnings

- Parses dry-run download archives across APT (`apt-get -s dist-upgrade`) and Flatpak (`flatpak remote-ls --columns=download-size`).
- Warns users when total download volume exceeds 1 GB (`⚠️ Large Download (> 1 GB)` badge in GUI and warnings in CLI before confirming).

### 7.12 In-app self-updater & GitHub release tracking (`SelfUpdater`)

- Queries GitHub Releases API with automated semantic version comparison against the running build.
- Shows release notes and provides 1-click automated downloading and installation of the updated `.deb` package directly within the app.
- Exposed via GUI Settings Dashboard ("ULUM Application Updates" card) and CLI `ulum self-update [--check]`.

### 7.13 Parallel, incremental, bounded engine (v0.4.0)

- Concurrently queries all enabled package managers (APT, Flatpak, Snap, AppImage) using Python `asyncio` and thread delegation.
- Enforces strict 30-second per-adapter timeouts so hanging remote repositories or network glitches do not freeze the tool.
- Reports failed or timed-out sources explicitly with elapsed runtime and error details (never silently reporting 0 updates).
- Caches inventory and update metadata in SQLite with a 1-hour TTL.

### 7.14 Security-first origin tagging (`--security-only`) (v0.4.0)

- Inspects the origin pocket of pending APT updates (via `apt list --upgradable`).
- Tags packages originating from `-security` pockets (e.g. `noble-security`) with `urgency = "Security"`.
- Allows upgrading only security-critical packages via `ulum update --security-only` without requiring a full distribution or bulk package upgrade.

### 7.15 P0 safety hardening for system modifications (v0.4.0)

- **AptRepoDoctor**: Automatic creation of pre-modification backups (`<file>.ulum-backup-<timestamp>`) before modifying any repo file, path allow-list enforcement restricted to `/etc/apt/sources.list*`, and 1-click restore (`ulum doctor --restore-repos`).
- **KernelCleaner**: Active booted kernel (`uname -r`) guard, strict minimum 2-kernel safety rule (running kernel + newest fallback) preventing unbootable systems, compiled DKMS driver inspection and warning, Timeshift/Snapper snapshot detection, and recovery instructions on partial purge failures.
- **SelfUpdater**: Cryptographic SHA256 checksum verification before installing release binaries/packages, local rollback preservation in `~/.local/share/ulum/rollback/`, and post-install launch smoke test.
- **AppImage Integration**: Collision detection and `.desktop.backup` preservation, path validation, and launcher unintegration (`ulum integrate --remove <id>`).

### 7.16 Comprehensive 8-point health diagnostics model v2 (`SystemDoctor`) (v0.4.0)

- Structured diagnostic inspection executing 8 ordered health checks:
  1. Distribution, kernel, architecture, and platform compatibility.
  2. Package manager availability (APT, Flatpak, Snap, AppImage).
  3. Repository health (active source counting, syntax checks, disabled entries).
  4. `/boot` partition storage and kernel inventory (critical alert if < 100 MB).
  5. SQLite database health, schema version (v2), and integrity check.
  6. Package manager lock health (active holding PIDs vs dead/stale lock files).
  7. Inventory scan freshness (checks if scan is older than 24h or missing).
  8. ULUM version and GitHub release check.
- Standardized exit codes (0 = healthy/degraded, 1 = failure, 2 = missing dependency) and pure JSON output (`ulum doctor --json`).
- Automated stale lock clearing (`ulum doctor --fix`) removing locks only if holding PID is dead, alongside `dpkg --configure -a` and `apt-get install -f -y`.

### 7.17 Native desktop GUI & transparent health score (v0.4.0)

- Replaces embedded WebKit2 browser with an instant, native GTK desktop application with 7 dedicated views: Home (Bento Dashboard), Updates, Installed, Leftovers, Diagnostics, History, and Settings.
- Transparent 0-100 Health Score starting at 100 with itemized, visible deductions per PRD §6.3:
  - Pending Security updates (-5 pts each, max -30)
  - Pending Critical updates (-4 pts each, max -20)
  - Broken/404 repositories (-10 to -20 pts)
  - `/boot` storage pressure (-10 pts)
  - Stale locks (-10 pts)
  - Stale scan (-10 pts)
  - Verified leftovers > 1 GB (-5 pts)
- Prominent disclosure on Home and Updates views: *"Security urgency tagging is APT-only in v0.4"*.

## 8. CLI command specification

Proposed executable: `ulum`

| Command | Purpose |
|---|---|
| `ulum scan` | Scan installed software and detected sources concurrently |
| `ulum check [--security-only]` | Check for available updates concurrently with per-source timings and download estimates |
| `ulum list [--updates] [--security-only]` | List installed application records or pending updates |
| `ulum sources` | Show detected package managers and status |
| `ulum info <identifier>` | Show details for a source-qualified application |
| `ulum update --dry-run` | Preview supported updates |
| `ulum update --all` | Update all eligible supported applications |
| `ulum update --security-only` | Update only Security and Critical updates (APT-only in v0.4) |
| `ulum update --source apt` | Update through one source |
| `ulum update <identifier>` | Update a selected application |
| `ulum integrate [path] [--all] [--remove <id>]` | Register standalone AppImages into system desktop menu or remove launchers |
| `ulum remove <identifier>` | Start standard uninstall |
| `ulum remove <identifier> --complete` | Build a complete-removal plan |
| `ulum remove <identifier> --dry-run` | Preview removal without changing the system |
| `ulum leftovers` | Find and classify possible leftovers |
| `ulum cleanup [--yes]` | Review and remove approved leftover candidates |
| `ulum cleanup --kernels [--yes]` | Purge obsolete Linux kernels and free `/boot` partition space |
| `ulum dependencies <identifier>` | Show dependency information |
| `ulum history` | Show update history |
| `ulum removal-history` | Show removal history |
| `ulum exclude <identifier>` | Exclude an application from bulk operations |
| `ulum config` | View or edit configuration |
| `ulum doctor [--fix] [--fix-repos] [--restore-repos] [--json]` | Diagnose health, repair locks, disable 404 PPAs, restore repo backups, and emit structured JSON |
| `ulum self-update [--check]` | Check for new ULUM releases on GitHub and apply updates |
| `ulum version` | Show ULUM version |

Because names can collide across sources, commands should support an unambiguous form such as `apt:firefox`, `flatpak:org.mozilla.firefox`, or a stable inventory ID. The exact identifier grammar should be finalized during CLI design.

### 8.1 Command behavior rules

- `ulum check` must not install updates.
- `ulum update` without an explicit target or `--all` should show help or ask for a target; it must not silently update everything.
- `--dry-run` must not modify package state or delete files.
- Destructive cleanup must require an interactive confirmation unless a carefully designed non-interactive approval mechanism is supplied.
- Non-interactive execution must fail safely when required approval is missing.
- Exit codes must distinguish success, partial failure, invalid input, missing dependency, and user cancellation.

## 9. Removal workflow and safety model

### 9.1 Removal workflow

```text
User selects application
          |
          v
Resolve unique application identity
          |
          v
Detect source and installation scope
          |
          v
Query native ownership and metadata
          |
          v
Analyze dependencies and associated data
          |
          v
Build immutable removal plan
          |
          v
Display exact operations and risk
          |
          v
User reviews and approves
          |
          v
Execute native uninstall
          |
          v
Re-check package and file ownership
          |
          v
Execute approved safe cleanup
          |
          v
Verify result and record history
```

### 9.2 Removal plan contents

Before execution, show:

- Application display name and unique identifier.
- Installation source and scope.
- Native uninstall command or operation description.
- Packages and dependencies proposed for removal.
- Exact file and directory paths proposed for cleanup.
- Ownership evidence for each path.
- Estimated disk space to be freed, when measurable.
- Whether user data will be deleted.
- Whether the operation is reversible or has a backup.
- Items that will be preserved or skipped.
- Any uncertainty or unsupported cleanup.

The executor must act only on the approved plan. If the system state changes between planning and execution, invalidate or revalidate the plan.

### 9.3 File ownership and cleanup rules

Potential locations include:

| Location | Typical category | Safety rule |
|---|---|---|
| `/usr/bin` | System executables | Never manually delete; use package manager ownership |
| `/usr/lib` | Shared and application libraries | Never manually delete; use package manager |
| `/usr/share` | Application resources | Verify package ownership |
| `/etc` | System configuration | Use package-manager purge behavior; review residuals |
| `/opt` | Vendor applications | Require manifest or verified vendor uninstaller |
| `~/.config` | User configuration | Require explicit user approval |
| `~/.local/share` | User data | Preserve by default; explicit approval required |
| `~/.cache` | Cache | Verify application association; explicit cleanup approval |
| `~/.local/bin` | User executables | Require manifest or exact user selection |
| `~/.local/share/applications` | Desktop entries | Verify exact application association |

Additional rules:

- Never delete an entire parent directory just because its name resembles the application.
- Never follow symlinks outside the approved cleanup scope.
- Check mount points and path traversal risks.
- Re-check ownership immediately before deletion.
- Do not remove files owned by another package or application.
- Do not delete personal documents automatically.
- If ownership is ambiguous, preserve the file and explain why.

### 9.4 Dependency cleanup

ULUM must:

1. Query the native package manager for dependency relationships.
2. Distinguish required, recommended, optional, and automatically installed packages where the source exposes that information.
3. Identify dependencies still required by other installed software.
4. Present proposed removals before execution.
5. Delegate actual dependency resolution and removal to the native package manager.
6. Record what the package manager reports as removed.

Never manually delete shared libraries or assume a dependency is unused based on its name.

### 9.5 Source-specific removal considerations

- **APT:** use native remove/purge behavior and preview eligible autoremove packages. Do not silently run broad autoremove.
- **Flatpak:** distinguish user/system installations; offer unused runtime cleanup separately; explain the consequences of deleting application data.
- **Snap:** use Snap's own removal and purge behavior; do not manually remove Snap-managed files or revisions.
- **AppImage:** remove only the selected file and verified, approved associated files; there is no universal AppImage uninstaller.
- **Manual/vendor installs:** require an installation manifest or reviewed vendor uninstall procedure. Unknown installations are inventory-only until a safe method is configured.

## 10. Security and privilege model

Security is a release-blocking requirement.

1. Run discovery and read-only operations without root whenever possible.
2. Request elevated privileges through PolicyKit (`pkexec`) for graphical execution, using a dedicated policy (`org.ulum.pkexec.policy`) with display authorization (`xhost +SI:localuser:root`) to eliminate terminal-password hangs in the GUI dashboard.
3. Automatically resolve invoking user context (`PKEXEC_UID` / `SUDO_USER`) so elevated processes preserve and update the user's local inventory database (`~/.local/share/ulum/ulum.db`) and configuration rather than isolating state to `/root`.
4. Never collect or store the user's sudo password.
5. Use subprocess argument arrays; do not construct shell commands from untrusted input.
6. Validate identifiers and paths.
7. Preserve native package-manager locks.
8. Do not execute arbitrary scripts unless explicitly configured and approved.
9. Require clear confirmation for destructive operations.
10. Protect essential system packages and critical paths.
11. Never silently remove packages, dependencies, configuration, or user data.
12. Use safe path handling, symlink checks, and ownership verification before file deletion.
13. Record operation results without logging secrets.
14. Fail closed when ownership or deletion safety cannot be established.

A dry-run preview is a planning aid, not a security boundary. The executor must independently validate every operation.

## 11. Architecture

Use a modular, adapter-based design.

```text
CLI / Optional TUI
        |
        v
Application Service Layer
        |
        +-------------------------------+
        |                               |
        v                               v
Update Orchestrator              Removal Orchestrator
        |                               |
        v                               v
Update Planner                   Removal Planner
        |                               |
        +---------------+---------------+
                        |
                        v
                 Adapter Interface
                        |
       +----------------+----------------+
       |                |                |
      APT             Flatpak           Snap
       |                |                |
    AppImage       Custom/Vendor    Future adapters
                        |
                        v
              Native System Tools
                        |
                        v
           Privilege / Logging / SQLite
```

### 11.1 Architectural principles

- Keep CLI/TUI separate from business logic.
- Use one adapter interface per package ecosystem.
- Use stable source-qualified application identities.
- Keep planning separate from execution.
- Use native package managers for package operations.
- Do not modify package-manager databases directly.
- Make adapters independently testable.
- Report unsupported capabilities explicitly.
- Keep the design extensible without making the MVP plugin system unnecessarily complex.

### 11.2 Suggested adapter contract

Each adapter should expose capabilities such as:

- `detect()`
- `list_installed()`
- `check_updates()`
- `plan_update(targets)`
- `execute_update(plan)`
- `plan_remove(target)`
- `execute_remove(plan)`
- `verify_state(target)`
- `get_dependencies(target)`

An adapter must declare unsupported operations rather than pretending to support them.

## 12. Recommended technology stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| CLI framework | Typer |
| Terminal rendering | Rich |
| Optional TUI | Textual or Rich-based interface |
| Database | SQLite |
| Configuration | TOML |
| Logging | Python standard logging |
| Testing | Pytest |
| Packaging | Debian package and/or pipx for suitable environments |
| Distribution | GitHub Releases |

Python is recommended for the first implementation because it integrates well with Linux command-line tools and supports rapid adapter development. A later Rust implementation is optional, not a requirement.

## 13. Data model

Use SQLite for inventory, settings, and operation history. Store only information needed for product functionality.

### 13.1 `applications`

- `id`
- `source`
- `source_scope`
- `package_id`
- `display_name`
- `installed_version`
- `install_location`
- `manifest_path`
- `update_supported`
- `remove_supported`
- `last_scanned_at`

Use a uniqueness constraint appropriate to source, scope, and package ID.

### 13.2 `updates`

- `id`
- `application_id`
- `current_version`
- `available_version`
- `detected_at`
- `status`
- `details`
- `urgency` (`Security`, `Critical`, `Feature`, `Optional`, `Unknown`)

### 13.3 `update_history`

- `id`
- `application_id`
- `source`
- `previous_version`
- `new_version`
- `status`
- `exit_code`
- `started_at`
- `finished_at`
- `error_summary`

### 13.4 `removal_history`

- `id`
- `application_id`
- `application_name_snapshot`
- `package_id_snapshot`
- `source`
- `source_scope`
- `removal_mode`
- `approved_plan_summary`
- `removed_items`
- `preserved_items`
- `status`
- `exit_code`
- `started_at`
- `finished_at`
- `error_summary`

### 13.5 `cleanup_candidates`

- `id`
- `application_id`
- `path`
- `candidate_type`
- `ownership_evidence`
- `confidence`
- `estimated_size`
- `review_status`
- `detected_at`

### 13.6 `settings`

- `key`
- `value`
- `updated_at`

### 13.7 `repo_fixes` (v0.4.0)

- `id`
- `file_path`
- `line_number`
- `line_text`
- `error`
- `first_failed_at`
- `second_failed_at`
- `backup_path`
- `status` (`disabled`, `restored`, `transient`)
- `created_at`
- `restored_at`

### 13.8 `kernel_cleans` (v0.4.0)

- `id`
- `kernel_release`
- `package_ids`
- `is_booted`
- `is_fallback`
- `estimated_freed_bytes`
- `actual_freed_bytes`
- `snapshot_tool`
- `snapshot_id`
- `snapshot_taken`
- `status`
- `started_at`
- `finished_at`
- `error_summary`

### 13.9 `appimage_integrations` (v0.4.0)

- `id`
- `binary_path`
- `desktop_path`
- `display_name`
- `backup_desktop_path`
- `status` (`integrated`, `replaced`, `stale`, `removed`)
- `created_at`
- `last_verified_at`

### 13.10 `download_estimates` (v0.4.0)

- `id`
- `scan_id`
- `source`
- `estimated_bytes`
- `estimated_at`
- `expires_at`
- `status`

### 13.11 `self_updates` (v0.4.0)

- `id`
- `from_version`
- `to_version`
- `release_url`
- `download_sha256`
- `verified`
- `rollback_artefact_path`
- `status`
- `started_at`
- `finished_at`
- `error_summary`

### 13.12 `operation_history` (v0.4.0)

Unified history table extending individual history tables:
- `id`
- `operation_type` (`update`, `remove`, `repo_fix`, `kernel_clean`, `integrate`, `self_update`, `snapshot`)
- `target_id`
- `source`
- `status`
- `exit_code`
- `approved_plan_summary`
- `backup_path`
- `snapshot_id`
- `started_at`
- `finished_at`
- `error_summary`

### 13.13 Database Migrations (v0.4.0)

Versioned migrations executed sequentially in `src/ulum/db/migrations.py` using `PRAGMA user_version`.

Avoid storing full file contents, secrets, or unnecessary personal data in the database.

## 14. Configuration

Configuration should support:

- Enabled/disabled adapters.
- Scan locations for AppImages and manual installations.
- Excluded application identifiers.
- Notification preferences.
- Log level and retention.
- Default confirmation behavior.
- Custom updater/uninstaller definitions.
- Database and cache locations.

Custom commands must be clearly marked as user-defined executable actions. They must not be imported or executed from untrusted metadata without explicit approval.

## 15. User experience

### 15.1 CLI principles

- Clear, concise output.
- Human-readable tables and progress.
- Machine-readable output such as JSON for scripting.
- Consistent exit codes.
- Helpful errors and recovery guidance.
- No hidden system modifications.

### 15.2 Optional TUI menu

```text
╔════════════════════════════════════════════╗
║       UNIVERSAL LINUX UPDATE MANAGER       ║
║                    ULUM                    ║
╚════════════════════════════════════════════╝

  1. Check for Updates
  2. Update Applications
  3. Installed Applications
  4. Uninstall Application
  5. Find Leftover Files
  6. Review and Clean Leftovers
  7. Update History
  8. Removal History
  9. System Diagnostics
 10. Settings
  0. Exit

Select an option:
```

The TUI is optional. Every core operation must remain available from the CLI.

## 16. Project structure

```text
universal-linux-update-manager/
├── pyproject.toml
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── INSTALLATION.md
│   ├── SECURITY.md
│   └── ADAPTERS.md
├── src/
│   └── ulum/
│       ├── __init__.py
│       ├── main.py
│       ├── cli.py
│       ├── core/
│       │   ├── system_info.py
│       │   ├── scanner.py
│       │   ├── checker.py
│       │   ├── updater.py
│       │   └── orchestrator.py
│       ├── adapters/
│       │   ├── base.py
│       │   ├── apt.py
│       │   ├── flatpak.py
│       │   ├── snap.py
│       │   ├── appimage.py
│       │   └── custom.py
│       ├── removal/
│       │   ├── planner.py
│       │   ├── analyzer.py
│       │   ├── dependency_manager.py
│       │   ├── file_detector.py
│       │   ├── cleanup.py
│       │   ├── verifier.py
│       │   └── safety.py
│       ├── database/
│       │   ├── models.py
│       │   ├── migrations.py
│       │   └── storage.py
│       ├── security/
│       │   ├── privileges.py
│       │   └── paths.py
│       ├── utils/
│       │   ├── logger.py
│       │   └── subprocess.py
│       └── tui/
│           └── dashboard.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── safety/
└── scripts/
    └── install.sh
```

## 17. Development roadmap

### Phase 1 — Foundation and read-only inventory

- CLI skeleton and configuration.
- Distribution and architecture detection.
- Adapter interface.
- APT, Flatpak, and Snap detection.
- Installed application inventory.
- Structured logging and SQLite migrations.
- Unit tests and mocked subprocess tests.

### Phase 2 — Update management

- Repository/metadata refresh workflow.
- Update discovery for APT, Flatpak, and Snap.
- Consolidated update report.
- Update previews.
- Individual and bulk update execution.
- Update history and failure handling.

### Phase 3 — Safe package removal

- Standard uninstall for APT, Flatpak, and Snap.
- Source-qualified application identity.
- Removal planner and immutable plan representation.
- Dependency analysis through native tools.
- Preview and confirmation.
- Removal verification and history.

### Phase 4 — Complete cleanup and leftovers

- Detect verified application-specific configuration and cache candidates.
- Classify verified, probable, and unknown leftovers.
- Selective cleanup with explicit approval.
- User-data protection.
- Path, symlink, and ownership safety tests.
- Recovery guidance for partial operations.

### Phase 5 — AppImage and custom integrations

- AppImage discovery.
- Supported updater integration.
- Registered manifests for manual applications.
- Custom updater and uninstaller definitions.
- No automatic deletion of unknown files.

### Phase 6 — User experience and distribution

- Optional TUI.
- Desktop notifications.
- JSON output.
- Debian packaging and installation documentation.
- GitHub releases.
- Compatibility testing and security review.

## 18. Testing requirements

### 18.1 Platforms

Test on:

- Linux Mint 22.x.
- Ubuntu 24.04 LTS.
- Clean virtual machines.
- Systems with all supported package managers.
- Systems with one or more package managers missing.
- Systems with user-scope and system-scope Flatpak installations.

### 18.2 Update tests

- No updates available.
- Updates available from one or multiple sources.
- Repository unavailable.
- Package manager missing.
- Insufficient privileges.
- Package-manager lock held.
- Interrupted or failed operation.
- Excluded application.
- Dry-run makes no changes.

### 18.3 Removal and cleanup tests

- Standard removal preserves user data as specified.
- Complete removal presents exact cleanup candidates.
- Shared dependency is retained.
- Unused dependency proposal is delegated to native package manager.
- Ambiguous file is preserved.
- Symlink cannot escape approved cleanup scope.
- Parent directories and unrelated files remain intact.
- User data is preserved unless explicitly approved.
- Package-manager failure produces a partial/failed status and recovery guidance.
- A stale removal plan is revalidated before execution.
- Dry-run performs no uninstall or deletion.

All destructive logic must be tested with temporary directories and mocked package-manager commands before testing against real systems. Integration tests should run in disposable virtual machines or containers where suitable.

## 19. Acceptance criteria

### 19.1 MVP acceptance

- [x] Detects Linux Mint and Ubuntu.
- [x] Detects APT, Flatpak, and Snap availability.
- [x] Inventories installed applications with source-qualified identifiers.
- [x] Checks updates across supported sources.
- [x] Reports source errors separately from zero updates.
- [x] Previews updates where supported.
- [x] Updates selected applications and all eligible applications.
- [x] Records update history.
- [x] Supports standard uninstall for APT, Flatpak, and Snap.
- [x] Previews removal operations.
- [x] Requires approval for destructive operations.
- [x] Protects shared dependencies and user data.
- [x] Handles missing package managers and operation failures.
- [x] Provides diagnostics and installation/uninstallation documentation.

### 19.2 Complete-removal acceptance

- [x] Offers a complete-removal plan.
- [x] Identifies configuration, cache, logs, and data candidates.
- [x] Distinguishes verified, probable, and unknown ownership.
- [x] Uses native dependency analysis.
- [x] Shows exact paths and proposed package removals.
- [x] Requires explicit approval for user-data deletion.
- [x] Never manually deletes package-managed shared libraries.
- [x] Revalidates paths and ownership before deletion.
- [x] Records removed and preserved items.
- [x] Verifies the resulting state.
- [x] Reports partial cleanup honestly.

## 20. Product decisions

| Decision | Initial policy |
|---|---|
| Replace native package managers? | No |
| Require root for scanning? | No, unless a specific source requires it |
| Install updates automatically? | Optional systemd scheduled updates (`ulum schedule`) |
| Update arbitrary binaries? | Supported for AppImage binaries in ~/Applications |
| Remove arbitrary binaries? | No; require a verified manifest or explicit safe procedure |
| Delete user data by default? | Never |
| Remove shared dependencies manually? | Never |
| Run broad autoremove silently? | Never |
| Perform cleanup without preview? | Never |
| Support multiple distributions? | Mint & Ubuntu full MVP, expandable |
| Provide GUI in MVP? | Implemented in v0.2+ (GTK3 + WebKit2 Dashboard) |

## 21. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Package-manager behavior differs by distribution | Adapter-specific implementations and distro integration tests |
| Same application appears in multiple sources | Source-qualified identity and duplicate-aware inventory |
| Update metadata is stale | Report metadata refresh time and refresh errors |
| Removal deletes unrelated files | Ownership evidence, exact-path preview, revalidation, and fail-closed behavior |
| Shared dependencies are removed | Native dependency resolver and explicit preview |
| Custom scripts are malicious or unsafe | Disabled by default; explicit registration and review |
| Interrupted operations leave partial state | Record partial status and provide native recovery guidance |
| “Complete removal” is misunderstood as absolute | Define it as the fullest verified safe cleanup, not a guarantee |

## 22. Future enhancements

- [x] GUI desktop application (GTK3 + WebKit2 glassmorphic dashboard).
- [x] Scheduled update checks and background automation (user systemd timer).
- [x] Health repair and auto-fix diagnostics (`ulum doctor --fix`).
- [ ] Optional filesystem snapshot integration (decoupled from default update workflow).
- [ ] Fedora, Arch, and openSUSE adapters (DNF, Pacman, Zypper).
- [ ] More application-specific updater integrations.
- [ ] System tray notifications.
- [ ] Security update prioritization.
- [ ] Exportable inventory, update, and removal reports.
- [ ] Rollback assistance where supported by the package manager or filesystem.
- [ ] Repository/source management with separate safety and trust requirements.

## 23. Recommended MVP scope

Keep the first release focused:

1. APT, Flatpak, and Snap detection and inventory.
2. Unified update checking.
3. Individual and bulk updates with previews.
4. Standard uninstall for supported package sources.
5. A safe removal planner.
6. Dependency review through native package managers.
7. Update and removal history.
8. Diagnostics, logging, and security tests.

Defer AppImage updates, arbitrary manual installations, and advanced custom cleanup until the package-based update and removal workflows are reliable.

## 24. Final product principle

ULUM is an orchestration and safety layer over existing Linux software-management systems—not a replacement for them.

Its most important promise is not that it can update or delete absolutely everything. Its promise is that it can clearly identify what it supports, explain what it plans to change, use the correct native mechanism, protect unrelated files and data, and report honestly when an operation is unsupported or incomplete.
