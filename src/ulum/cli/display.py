from typing import Dict, List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from ulum.core.models import (
    ApplicationRecord,
    CleanupCandidate,
    RemovalPlan,
    SystemInfo,
    UpdateRecord,
)

console = Console()

def format_bytes(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size) < 1024.0:
            return f"{size:3.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def print_system_info(info: SystemInfo, managers: Dict[str, bool]) -> None:
    table = Table(show_header=False, box=None)
    table.add_row("[bold]Distribution:[/bold]", f"{info.distro_name} {info.distro_version} ({info.distro_id})")
    table.add_row("[bold]Architecture:[/bold]", info.arch)
    table.add_row("[bold]Kernel:[/bold]", info.kernel)
    table.add_row("[bold]Supported Host:[/bold]", "[green]Yes[/green]" if info.is_supported else "[yellow]Experimental/Untested[/yellow]")
    
    mgr_str = ", ".join(f"[green]{k}[/green]" if v else f"[dim]{k} (not found)[/dim]" for k, v in managers.items())
    table.add_row("[bold]Package Managers:[/bold]", mgr_str)
    console.print(Panel(table, title="[bold]System Status[/bold]", border_style="cyan"))

def print_inventory_table(apps: List[ApplicationRecord], title: str = "Installed Applications") -> None:
    table = Table(title=title, border_style="dim")
    table.add_column("Qualified ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Source", style="magenta")
    table.add_column("Scope", style="blue")
    table.add_column("Version", style="green")

    for app in apps:
        table.add_row(
            app.qualified_id,
            app.display_name,
            app.source.value,
            app.source_scope.value,
            app.installed_version,
        )
    console.print(table)
    console.print(f"[dim]Total records: {len(apps)}[/dim]\n")

def print_updates_table(updates: List[UpdateRecord]) -> None:
    if not updates:
        console.print("[green]✓ System is completely up to date. No updates pending.[/green]\n")
        return

    table = Table(title="Available Updates", border_style="cyan")
    table.add_column("Qualified ID", style="cyan", no_wrap=True)
    table.add_column("Source", style="magenta")
    table.add_column("Current Version", style="yellow")
    table.add_column("Available Version", style="green")

    for upd in updates:
        table.add_row(
            upd.application.qualified_id,
            upd.application.source.value,
            upd.application.installed_version,
            upd.available_version,
        )
    console.print(table)
    console.print(f"[bold]Total update candidates: {len(updates)}[/bold]\n")

def print_removal_plan(plan: RemovalPlan) -> None:
    console.print(f"\n[bold red]── Proposed Removal Plan for {plan.application.qualified_id} ──[/bold red]")
    console.print(f"[bold]Removal Mode:[/bold] {'Complete (Purge + Data Clean)' if plan.complete else 'Standard'}")
    console.print(f"[bold]Native Command:[/bold] [yellow]{' '.join(plan.native_command)}[/yellow]")
    console.print(f"[bold]Packages to remove:[/bold] {', '.join(plan.packages_to_remove)}")

    if plan.dependencies_to_remove:
        console.print(f"[bold]Dependencies to autoremove:[/bold] {', '.join(plan.dependencies_to_remove)}")

    if plan.cleanup_items:
        console.print("\n[bold]Residual paths scheduled for deletion:[/bold]")
        for item in plan.cleanup_items:
            console.print(f"  • [red]{item.path}[/red] ({format_bytes(item.estimated_size_bytes)}) - {item.evidence}")
        console.print(f"[bold]Total space to free:[/bold] ~{format_bytes(plan.estimated_freed_bytes)}")

    if plan.preserved_items:
        console.print(f"[bold dim]Preserved locations:[/bold dim] [dim]{', '.join(plan.preserved_items)}[/dim]")

    if plan.safety_warnings:
        console.print("\n[bold yellow]Safety Warnings:[/bold yellow]")
        for w in plan.safety_warnings:
            console.print(f"  [yellow]⚠ {w}[/yellow]")
    console.print()

def print_leftovers_table(candidates: List[CleanupCandidate]) -> None:
    if not candidates:
        console.print("[green]✓ No residual leftover files found.[/green]\n")
        return

    table = Table(title="Residual Leftover Candidates", border_style="yellow")
    table.add_column("Path", style="red")
    table.add_column("Type", style="cyan")
    table.add_column("Confidence", style="bold")
    table.add_column("Est. Size", style="green")
    table.add_column("Evidence", style="dim")

    for c in candidates:
        table.add_row(
            str(c.path),
            c.candidate_type,
            c.confidence.value.upper(),
            format_bytes(c.estimated_size_bytes),
            c.evidence,
        )
    console.print(table)
    console.print(f"[dim]Total leftover candidates: {len(candidates)}[/dim]\n")

def print_history_table(history: List[dict], kind: str = "update") -> None:
    if not history:
        console.print(f"[dim]No {kind} history recorded yet.[/dim]\n")
        return

    table = Table(title=f"{kind.capitalize()} History", border_style="blue")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Source", style="magenta")
    table.add_column("Package ID", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Date", style="dim")

    for row in history:
        status_color = "green" if row.get("status") == "success" else "red"
        status_str = f"[{status_color}]{row.get('status')}[/{status_color}]"
        table.add_row(
            str(row.get("id")),
            row.get("source", ""),
            row.get("package_id", ""),
            status_str,
            str(row.get("started_at", ""))[:19],
        )
    console.print(table)
