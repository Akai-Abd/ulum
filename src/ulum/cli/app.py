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
from ulum.core.orchestrator import Orchestrator
from ulum.core.system import detect_package_managers, get_system_info
from ulum.db.database import get_db_path, init_db
from ulum.db.repository import Repository
from ulum.removal.leftovers import LeftoverScanner
from ulum.removal.safety import SafetyValidator

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
):
    """Check for available updates across all supported sources."""
    orc = get_orchestrator()
    with console.status("[bold cyan]Checking for available updates...[/bold cyan]"):
        updates = orc.check_updates(refresh=refresh, source=source)
    print_updates_table(updates)

@app.command("list")
def list_cmd(
    updates_only: bool = typer.Option(False, "--updates", "-u", help="Show only applications with available updates"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Filter by source (apt, flatpak, snap)"),
):
    """List installed applications or pending updates."""
    orc = get_orchestrator()
    if updates_only:
        upds = orc.repo.get_updates(source=source)
        if not upds:
            console.print("[dim]No updates recorded. Run 'ulum check' to scan for new updates.[/dim]")
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
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Simulate update without modifying the system"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip interactive confirmation"),
):
    """Update a specific application, a single source, or all eligible software."""
    if not identifier and not all_packages and not source:
        console.print("[yellow]Please specify an application ID, --source <name>, or --all to proceed.[/yellow]")
        console.print("Run [bold]ulum update --help[/bold] for usage.")
        raise typer.Exit(code=1)

    orc = get_orchestrator()
    targets = [identifier] if identifier else None

    if dry_run:
        console.print("[bold yellow]Running in DRY-RUN mode. No changes will be made.[/bold yellow]")

    if not yes and not dry_run:
        target_desc = identifier or (f"all {source} packages" if source else "ALL eligible packages")
        if not Confirm.ask(f"Proceed with updating {target_desc}?"):
            console.print("[dim]Update cancelled by user.[/dim]")
            raise typer.Exit(code=0)

    results = orc.execute_updates(targets=targets, source=source, dry_run=dry_run)
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
    scanner = LeftoverScanner(orc.repo)
    with console.status("[bold cyan]Scanning for residual leftover candidates...[/bold cyan]"):
        candidates = scanner.scan_leftovers()
    orc.repo.save_cleanup_candidates(candidates, source="system", package_id="<residual>")
    print_leftovers_table(candidates)

@app.command("cleanup")
def cleanup_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation for verified leftovers"),
):
    """Review and remove verified residual leftover files."""
    orc = get_orchestrator()
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
        p = c["path"]
        is_valid, reason = SafetyValidator.validate_cleanup_path(p)
        if is_valid:
            try:
                shutil.rmtree(p)
                orc.repo.mark_candidate_removed(p)
                console.print(f"[green]✓ Deleted:[/green] {p}")
            except Exception as e:
                console.print(f"[red]Failed to delete {p}:[/red] {e}")
        else:
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
def doctor_cmd():
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
    console.print("\n[bold green]✓ Diagnostic check complete.[/bold green]")
