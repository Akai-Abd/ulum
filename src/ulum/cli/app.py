from pathlib import Path
import shutil
from typing import Optional
import typer
from rich.prompt import Confirm
from ulum import __version__
from ulum.cli.display import (
    console,
    print_history_table,
    print_inventory_table,
    print_leftovers_table,
    print_removal_plan,
    print_system_info,
    print_updates_table,
)
from ulum.core.config import load_config
from ulum.core.models import is_security_only
from ulum.core.orchestrator import Orchestrator
from ulum.core.system import detect_package_managers, get_system_info
from ulum.db.database import get_db_path, init_db
from ulum.db.repository import Repository
from ulum.doctor.repos import AptRepoDoctor
from ulum.removal.kernels import KernelCleaner
from ulum.adapters.appimage import AppImageAdapter
from ulum.removal.leftovers import LeftoverScanner
from ulum.removal.safety import SafetyValidator
from ulum.utils.self_update import SelfUpdater

app = typer.Typer(
    name="ulum",
    help="Universal Linux Update Manager: Orchestrates updates and safe removals across APT, Flatpak, and Snap.",
    add_completion=False,
)

def get_orchestrator() -> Orchestrator:
    conn = init_db()
    repo = Repository(conn)
    config = load_config()
    return Orchestrator(repo=repo, config=config)

@app.command("gui")
def gui_cmd():
    """Launch the graphical user interface as root."""
    import os
    import shutil
    if os.geteuid() != 0 and shutil.which("pkexec"):
        gui_bin = shutil.which("ulum-gui")
        if gui_bin:
            os.execvp("pkexec", ["pkexec", gui_bin])
    from ulum.gui.window import run_gui
    run_gui()

@app.command("version")
def version_cmd():
    """Show ULUM version and host environment."""
    info = get_system_info()
    console.print(f"[bold cyan]ULUM[/bold cyan] version [bold green]{__version__}[/bold green]")
    console.print(f"Host: {info.distro_name} {info.distro_version} ({info.arch})")

@app.command("sources")
def sources_cmd():
    """Show detected package managers and system status."""
    info = get_system_info()
    managers = detect_package_managers()
    print_system_info(info, managers)

@app.command("scan")
def scan_cmd():
    """Scan and index all installed applications from active sources."""
    orc = get_orchestrator()
    with console.status("[bold cyan]Scanning installed software...[/bold cyan]"):
        counts = orc.scan_all()
    
    total = sum(counts.values())
    console.print(f"[bold green]✓ Scan complete.[/bold green] Indexed {total} applications:")
    for src, count in counts.items():
        console.print(f"  • [cyan]{src.upper()}:[/cyan] {count} packages")

@app.command("check")
def check_cmd(
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Refresh repository metadata before checking"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Filter check to a specific source (apt, flatpak, snap)"),
    security_only: bool = typer.Option(False, "--security-only", help="Filter check to only Security and Critical updates"),
):
    """Check for available updates across all supported sources concurrently."""
    orc = get_orchestrator()
    with console.status("[bold cyan]Checking for available updates concurrently...[/bold cyan]"):
        detailed = orc.check_updates_detailed(refresh=refresh, source=source)
        updates = detailed["updates"]
        source_status = detailed.get("source_status", {})
        is_cached = detailed.get("is_cached", False)
        cache_age = detailed.get("cache_age_seconds", 0.0)

    if security_only:
        updates = [u for u in updates if is_security_only(getattr(u, "urgency", "Unknown"))]

    if is_cached:
        console.print(f"[dim]Showing cached results from {int(cache_age // 60)}m ago. Use --refresh to re-query upstream sources.[/dim]\n")
    elif source_status:
        for src, st in source_status.items():
            if st["status"] == "success":
                console.print(f"  • [cyan]{src.upper()}:[/cyan] {st['count']} updates found [dim]({st['elapsed']:.2f}s)[/dim]")
            else:
                console.print(f"  • [red]{src.upper()}:[/red] Failed: {st['error']} [dim]({st['elapsed']:.2f}s)[/dim]")
        console.print("")

    print_updates_table(updates)
    if updates:
        dl_summary = orc.get_update_download_summary()
        if dl_summary["total_bytes"] > 0:
            console.print(f"  • [cyan]Estimated Download Size:[/cyan] [bold]{dl_summary['formatted_size']}[/bold]")
            if dl_summary["is_large_download"]:
                console.print(f"    [bold yellow]⚠️ {dl_summary['warning']}[/bold yellow]")

@app.command("list")
def list_cmd(
    updates_only: bool = typer.Option(False, "--updates", "-u", help="Show only applications with available updates"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Filter by source (apt, flatpak, snap)"),
    security_only: bool = typer.Option(False, "--security-only", help="Filter to only Security and Critical updates"),
):
    """List installed applications or pending updates."""
    orc = get_orchestrator()
    if updates_only:
        upds = orc.repo.get_updates(source=source)
        if security_only:
            upds = [u for u in upds if is_security_only(u.get("urgency", "Unknown"))]
        if not upds:
            msg = "No security updates recorded." if security_only else "No updates recorded. Run 'ulum check' to scan for new updates."
            console.print(f"[dim]{msg}[/dim]")
            return
        # Display simplified updates
        from ulum.core.models import ApplicationRecord, ScopeType, SourceType, UpdateRecord
        records = [
            UpdateRecord(
                application=ApplicationRecord(
                    source=SourceType(u["source"]),
                    source_scope=ScopeType.SYSTEM,
                    package_id=u["package_id"],
                    display_name=u.get("display_name") or u["package_id"],
                    installed_version=u["current_version"],
                ),
                available_version=u["available_version"],
                urgency=u.get("urgency", "Unknown"),
            )
            for u in upds
        ]
        print_updates_table(records)
    else:
        apps = orc.repo.get_applications(source=source)
        if not apps:
            console.print("[yellow]Inventory empty. Run 'ulum scan' first to index installed packages.[/yellow]")
            return
        print_inventory_table(apps)

@app.command("info")
def info_cmd(identifier: str = typer.Argument(..., help="Qualified package ID (e.g. apt:curl or flatpak:org.mozilla.firefox)")):
    """Show details for a source-qualified application."""
    orc = get_orchestrator()
    app_rec = orc.repo.get_application_by_id(identifier)
    if not app_rec:
        console.print(f"[red]Error:[/red] Application '{identifier}' not found in inventory. Run 'ulum scan' to refresh.")
        raise typer.Exit(code=1)

    console.print(f"\n[bold cyan]Application Details: {app_rec.qualified_id}[/bold cyan]")
    console.print(f"  • Name: [bold]{app_rec.display_name}[/bold]")
    console.print(f"  • Source: [magenta]{app_rec.source.value}[/magenta] (Scope: {app_rec.source_scope.value})")
    console.print(f"  • Installed Version: [green]{app_rec.installed_version}[/green]")
    console.print(f"  • Install Location: {app_rec.install_location or 'Native default'}")
    console.print(f"  • Update Supported: {'Yes' if app_rec.update_supported else 'No'}")
    console.print(f"  • Removal Supported: {'Yes' if app_rec.remove_supported else 'No'}\n")

@app.command("update")
def update_cmd(
    identifier: Optional[str] = typer.Argument(None, help="Target application ID to update"),
    all_packages: bool = typer.Option(False, "--all", "-a", help="Update all eligible packages across all sources"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Update all packages for a specific source"),
    security_only: bool = typer.Option(False, "--security-only", help="Update only Security and Critical updates"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Simulate update without modifying the system"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip interactive confirmation"),
):
    """Update a specific application, a single source, or all eligible software."""
    if not identifier and not all_packages and not source and not security_only:
        console.print("[yellow]Please specify an application ID, --source <name>, --security-only, or --all to proceed.[/yellow]")
        console.print("Run [bold]ulum update --help[/bold] for usage.")
        raise typer.Exit(code=1)

    orc = get_orchestrator()
    targets = [identifier] if identifier else None

    if dry_run:
        console.print("[bold yellow]Running in DRY-RUN mode. No changes will be made.[/bold yellow]")

    if security_only:
        console.print("[bold cyan]Filtering exclusively to Security and Critical updates (APT-only in v0.4)...[/bold cyan]")

    dl_summary = orc.get_update_download_summary()
    if dl_summary["is_large_download"]:
        console.print(f"[bold yellow]⚠️ Metered Connection Warning:[/bold yellow] Large download of {dl_summary['formatted_size']} required.")

    if not yes and not dry_run:
        if security_only:
            target_desc = "all pending SECURITY and CRITICAL packages"
        else:
            target_desc = identifier or (f"all {source} packages" if source else "ALL eligible packages")
        if not Confirm.ask(f"Proceed with updating {target_desc}?"):
            console.print("[dim]Update cancelled by user.[/dim]")
            raise typer.Exit(code=0)

    results = orc.execute_updates(
        targets=targets, source=source, security_only=security_only, dry_run=dry_run
    )
    if not results and security_only:
        console.print("[green]✓ No pending security updates found.[/green]")
        return

    for src, res in results:
        if res.success:
            console.print(f"[bold green]✓ {src.upper()} update succeeded.[/bold green]")
        else:
            console.print(f"[bold red]✗ {src.upper()} update failed (exit code {res.exit_code}):[/bold red] {res.error_summary or res.stderr}")

@app.command("remove")
def remove_cmd(
    identifier: str = typer.Argument(..., help="Qualified ID of application to uninstall (e.g. apt:gimp)"),
    complete: bool = typer.Option(False, "--complete", "-c", help="Perform complete removal (purge config and verified data)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview removal plan without changing system"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip interactive confirmation"),
):
    """Safely uninstall an application using its native package manager."""
    orc = get_orchestrator()
    try:
        app_rec, plan = orc.plan_removal(identifier, complete=complete)
    except Exception as e:
        console.print(f"[bold red]Error planning removal:[/bold red] {e}")
        raise typer.Exit(code=1)

    print_removal_plan(plan)

    if dry_run:
        console.print("[bold yellow]Dry-run complete. No changes were made.[/bold yellow]")
        raise typer.Exit(code=0)

    if not plan.is_safe:
        console.print("[bold red]Action aborted:[/bold red] Removal plan flagged as unsafe due to critical dependencies.")
        raise typer.Exit(code=1)

    if not yes:
        prompt_text = f"Confirm removal of {app_rec.qualified_id} ({'COMPLETE' if complete else 'STANDARD'})?"
        if not Confirm.ask(prompt_text):
            console.print("[dim]Operation cancelled by user.[/dim]")
            raise typer.Exit(code=0)

    with console.status("[bold red]Executing uninstallation...[/bold red]"):
        res = orc.execute_removal(plan, dry_run=False)

    if res.success:
        console.print(f"[bold green]✓ Uninstallation of {app_rec.qualified_id} succeeded.[/bold green]")
        if res.removed_items:
            console.print(f"[dim]Removed items: {', '.join(res.removed_items)}[/dim]")
    else:
        console.print(f"[bold red]✗ Removal failed (exit code {res.exit_code}):[/bold red] {res.error_summary or res.stderr}")
        raise typer.Exit(code=res.exit_code or 1)

@app.command("leftovers")
def leftovers_cmd():
    """Discover unassociated cache, configuration, or data leftovers."""
    orc = get_orchestrator()
    scanner = LeftoverScanner(orc.repo, adapters=orc.adapters)
    with console.status("[bold cyan]Scanning for residual leftover candidates...[/bold cyan]"):
        candidates = scanner.scan_leftovers()
    orc.repo.save_cleanup_candidates(candidates, source="system", package_id="<residual>")
    print_leftovers_table(candidates)

@app.command("cleanup")
def cleanup_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation for verified leftovers or kernels"),
    kernels: bool = typer.Option(False, "--kernels", "-k", help="Purge obsolete Linux kernels and free /boot partition space"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Simulate cleanup without modifying the system"),
):
    """Review and remove verified residual leftover files or obsolete Linux kernels."""
    orc = get_orchestrator()
    if kernels:
        console.print("[bold cyan]Scanning for obsolete Linux kernels...[/bold cyan]")
        plan = KernelCleaner.plan_cleanup()
        console.print(f"  • Running Kernel: [bold green]{plan['running_kernel']}[/bold green] (Protected)")
        console.print(f"  • Kept Kernels: [green]{', '.join(plan['kept_kernels'])}[/green]")
        if not plan["packages_to_remove"]:
            console.print("[green]✓ System is clean. No obsolete kernels found.[/green]")
            return
        console.print(f"  • Obsolete Packages to Purge ({len(plan['packages_to_remove'])}): [red]{', '.join(plan['packages_to_remove'])}[/red]")
        console.print(f"  • Estimated Freed Disk Space: [bold green]{plan['formatted_freed']}[/bold green]")
        if dry_run:
            console.print("[bold yellow]Dry-run mode: No packages were purged.[/bold yellow]")
            return
        if not yes:
            if not Confirm.ask(f"Purge these {len(plan['packages_to_remove'])} obsolete kernel packages?"):
                console.print("[dim]Kernel cleanup cancelled.[/dim]")
                return
        with console.status("[bold red]Purging obsolete kernel packages...[/bold red]"):
            res = KernelCleaner.execute_cleanup(plan, dry_run=False)
        if res.success:
            console.print(f"[bold green]✓ Successfully cleaned old kernels. Freed ~{plan['formatted_freed']}.[/bold green]")
        else:
            console.print(f"[bold red]✗ Kernel purge failed:[/bold red] {res.error_summary or res.stderr}")
        return

    candidates = orc.repo.get_cleanup_candidates(confidence="verified")
    if not candidates:
        console.print("[green]✓ No verified leftovers pending cleanup.[/green]")
        return

    console.print(f"[bold yellow]Found {len(candidates)} verified leftover candidate(s):[/bold yellow]")
    for c in candidates:
        console.print(f"  • [red]{c['path']}[/red] ({c['candidate_type']}) - {c['evidence']}")

    if not yes:
        if not Confirm.ask("Permanently delete these verified leftover directories?"):
            console.print("[dim]Cleanup cancelled.[/dim]")
            return

    for c in candidates:
        p = Path(c["path"])
        is_valid, reason = SafetyValidator.validate_cleanup_path(p)
        if is_valid and p.exists():
            try:
                if p.is_dir() and not p.is_symlink():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                orc.repo.mark_candidate_removed(str(p))
                console.print(f"[green]✓ Deleted:[/green] {p}")
            except Exception as e:
                console.print(f"[red]Failed to delete {p}:[/red] {e}")
        elif not is_valid:
            console.print(f"[yellow]Skipped {p}:[/yellow] {reason}")

@app.command("dependencies")
def dependencies_cmd(identifier: str = typer.Argument(..., help="Package ID to inspect (e.g. apt:vlc)")):
    """Inspect native package dependencies and reverse dependencies."""
    orc = get_orchestrator()
    if ":" in identifier:
        src, pkg = identifier.split(":", 1)
    else:
        app_rec = orc.repo.get_application_by_id(identifier)
        src, pkg = (app_rec.source.value, app_rec.package_id) if app_rec else ("apt", identifier)

    adapter = orc.adapters.get(src)
    if not adapter or not adapter.is_available():
        console.print(f"[red]Error:[/red] Adapter for source '{src}' is not available.")
        raise typer.Exit(code=1)

    deps = adapter.get_dependencies(pkg)
    console.print(f"\n[bold cyan]Dependency Inspection for {src}:{pkg}[/bold cyan]")
    for dep_type, items in deps.items():
        console.print(f"[bold]{dep_type.capitalize()} ({len(items)}):[/bold]")
        if items:
            for item in items[:25]:
                console.print(f"  • {item}")
            if len(items) > 25:
                console.print(f"  [dim]... and {len(items) - 25} more[/dim]")
        else:
            console.print("  [dim]None reported[/dim]")
    console.print()

@app.command("history")
def history_cmd(limit: int = typer.Option(20, "--limit", "-l", help="Number of records to display")):
    """Show update history."""
    orc = get_orchestrator()
    hist = orc.repo.get_update_history(limit=limit)
    print_history_table(hist, kind="update")

@app.command("removal-history")
def removal_history_cmd(limit: int = typer.Option(20, "--limit", "-l", help="Number of records to display")):
    """Show uninstallation and cleanup history."""
    orc = get_orchestrator()
    hist = orc.repo.get_removal_history(limit=limit)
    print_history_table(hist, kind="removal")

@app.command("doctor")
def doctor_cmd(
    fix: bool = typer.Option(False, "--fix", "-f", help="Attempt automatic repair of interrupted dpkg/apt locks and state"),
    fix_repos: bool = typer.Option(False, "--fix-repos", help="Scan for and disable broken or 404 APT repositories"),
):
    """Diagnose system compatibility, package managers, and database health."""
    console.print("[bold cyan]Running ULUM Health Diagnostics...[/bold cyan]\n")
    info = get_system_info()
    console.print(f"Distribution: {info.distro_name} {info.distro_version}")
    console.print(f"Supported Platform: {'[green]Yes[/green]' if info.is_supported else '[yellow]Untested/Experimental[/yellow]'}")

    mgrs = detect_package_managers()
    console.print("\nPackage Managers:")
    for name, ok in mgrs.items():
        console.print(f"  • {name.upper()}: {'[green]Available[/green]' if ok else '[dim]Not Found[/dim]'}")

    db_path = get_db_path()
    console.print(f"\nDatabase Storage: {db_path} ([green]Writable[/green])")
    
    # Check permissions
    from ulum.utils.process import command_exists, is_root
    sudo_ok = is_root() or command_exists("sudo")
    console.print(f"Privilege Escalation (sudo/root): {'[green]OK[/green]' if sudo_ok else '[red]Missing sudo[/red]'}")

    if fix or fix_repos:
        if fix_repos:
            console.print("\n[bold yellow]Diagnosing APT repository health (detecting 404s/broken keys)...[/bold yellow]")
            repo_res = AptRepoDoctor.fix_all_broken(dry_run=False)
            if repo_res["found_count"] == 0:
                console.print("[green]✓ All APT repositories are healthy (no 404 errors detected).[/green]")
            else:
                console.print(f"[bold green]✓ Disabled {repo_res['disabled_count']} broken/404 repository entry(s):[/bold green]")
                for d in repo_res["disabled_entries"]:
                    console.print(f"  • Disabled in [cyan]{Path(d['file']).name}:{d['line_number']}[/cyan] ({d['reason']})")

        if fix:
            console.print("\n[bold yellow]Attempting automated package manager recovery...[/bold yellow]")
            from ulum.utils.process import command_exists, run_cmd
            if command_exists("dpkg") and command_exists("apt-get"):
                try:
                    console.print("  • Configuring pending packages (dpkg --configure -a)...")
                    run_cmd(["dpkg", "--configure", "-a"], require_root=True)
                    console.print("  • Resolving broken dependencies (apt-get install -f)...")
                    run_cmd(["apt-get", "install", "-f", "-y"], require_root=True)
                    console.print("[bold green]✓ Automated recovery tasks completed successfully.[/bold green]")
                except Exception as e:
                    console.print(f"[bold red]Recovery encountered an error:[/bold red] {e}")
            else:
                console.print("[yellow]Automated recovery is currently only available for Debian/Ubuntu (APT) systems.[/yellow]")

    console.print("\n[bold green]✓ Diagnostic check complete.[/bold green]")

@app.command("schedule")
def schedule_cmd(
    install: bool = typer.Option(False, "--install", "-i", help="Install daily background update notification timer via systemd"),
    uninstall: bool = typer.Option(False, "--uninstall", "-u", help="Remove background update notification timer"),
    status: bool = typer.Option(False, "--status", "-s", help="Check status of background update timer"),
):
    """Manage automated background update checks and desktop notifications."""
    import subprocess
    systemd_user = Path.home() / ".config" / "systemd" / "user"
    service_file = systemd_user / "ulum-check.service"
    timer_file = systemd_user / "ulum-check.timer"

    if uninstall:
        if timer_file.exists():
            subprocess.run(["systemctl", "--user", "disable", "--now", "ulum-check.timer"], capture_output=True)
            timer_file.unlink(missing_ok=True)
            service_file.unlink(missing_ok=True)
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
            console.print("[bold green]✓ Background update check timer removed.[/bold green]")
        else:
            console.print("[dim]No active timer was found.[/dim]")
        return

    if not install or status:
        res = subprocess.run(["systemctl", "--user", "is-active", "ulum-check.timer"], capture_output=True, text=True)
        is_active = res.stdout.strip() == "active"
        console.print(f"Background Update Timer: {'[green]Active (Running)[/green]' if is_active else '[yellow]Inactive[/yellow]'}")
        if not is_active:
            console.print("[dim]Run 'ulum schedule --install' to enable daily background update checks.[/dim]")
        return

    systemd_user.mkdir(parents=True, exist_ok=True)
    ulum_bin = shutil.which("ulum") or f"{Path.home()}/.local/bin/ulum"
    service_content = f"""[Unit]
Description=ULUM Daily Background Update Checker
After=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c '{ulum_bin} check && UPDATES=$({ulum_bin} list -u | grep -E "apt|flatpak|snap" | wc -l); if [ "$UPDATES" -gt 0 ]; then notify-send "ULUM Updates Available" "$UPDATES updates are ready for installation." --icon=software-update-available; fi'
"""
    timer_content = """[Unit]
Description=Run ULUM background check daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
"""
    service_file.write_text(service_content, encoding="utf-8")
    timer_file.write_text(timer_content, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "ulum-check.timer"], capture_output=True)
    console.print("[bold green]✓ Background update notification timer installed and activated.[/bold green]")
    console.print("ULUM will silently check daily and display a desktop notification when updates arrive.")

@app.command("integrate")
def integrate_cmd(
    path: Optional[str] = typer.Argument(None, help="Path to AppImage file to integrate into desktop launcher"),
    all_appimages: bool = typer.Option(False, "--all", "-a", help="Scan and integrate all unintegrated AppImages"),
):
    """Integrate standalone AppImage applications into desktop start menu and launcher."""
    if path:
        p = Path(path)
        ok, msg, dfile = AppImageAdapter.integrate_appimage(p)
        if ok:
            console.print(f"[bold green]✓ {msg}[/bold green] (Created: {dfile})")
        else:
            console.print(f"[bold red]✗ Integration failed:[/bold red] {msg}")
    elif all_appimages:
        results = AppImageAdapter.integrate_all_unintegrated()
        if not results:
            console.print("[green]✓ No unintegrated AppImages found in ~/Downloads or ~/Applications.[/green]")
        else:
            console.print(f"[bold green]✓ Integrated {len(results)} AppImage(s):[/bold green]")
            for r in results:
                status = "[green]✓[/green]" if r["success"] else "[red]✗[/red]"
                console.print(f"  {status} {r['name']}: {r['message']}")
    else:
        unintegrated = AppImageAdapter.find_unintegrated_appimages()
        if not unintegrated:
            console.print("[green]✓ All detected AppImages are already integrated into desktop launcher.[/green]")
        else:
            console.print(f"[yellow]Found {len(unintegrated)} unintegrated AppImage(s):[/yellow]")
            for u in unintegrated:
                console.print(f"  • {u}")
            console.print("\nRun [bold]ulum integrate --all[/bold] to integrate all into your application menu.")

@app.command("self-update")
def self_update_cmd(
    check: bool = typer.Option(False, "--check", "-c", help="Only check for updates without installing"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation when installing update"),
):
    """Check for new ULUM releases on GitHub and apply updates."""
    with console.status("[bold cyan]Checking GitHub for ULUM updates...[/bold cyan]"):
        res = SelfUpdater.check_latest_release()

    if not res.get("success"):
        console.print(f"[bold red]Could not check for updates:[/bold red] {res.get('error')}")
        return

    console.print(f"Current ULUM Version: [bold cyan]v{res['current_version']}[/bold cyan]")
    console.print(f"Latest Online Release: [bold green]{res['tag_name']}[/bold green]")

    if not res.get("update_available"):
        console.print("[bold green]✓ ULUM is up to date! You are on the latest release.[/bold green]")
        return

    console.print(f"\n[bold yellow]★ New Version Available: {res['tag_name']}[/bold yellow]")
    if res.get("deb_filename"):
        console.print(f"Package: [cyan]{res['deb_filename']}[/cyan]")
    if res.get("release_url"):
        console.print(f"Release URL: {res['release_url']}")

    if check:
        return

    deb_url = res.get("download_url")
    if not deb_url:
        console.print("[yellow]No .deb package asset found for automated installation. Please visit the release URL.[/yellow]")
        return

    if not yes:
        if not Confirm.ask(f"Download and upgrade ULUM to {res['tag_name']} now?"):
            console.print("[dim]Update cancelled.[/dim]")
            return

    with console.status(f"[bold green]Downloading and installing ULUM {res['tag_name']}...[/bold green]"):
        install_res = SelfUpdater.apply_update(deb_url)

    if install_res.success:
        console.print(f"[bold green]✓ Successfully upgraded ULUM to {res['tag_name']}![/bold green]")
    else:
        console.print(f"[bold red]✗ Upgrade failed:[/bold red] {install_res.error_summary or install_res.stderr}")
