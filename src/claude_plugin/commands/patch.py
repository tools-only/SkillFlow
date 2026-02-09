"""Patch management commands for X-Skills Claude Code plugin.

Provides commands for listing, installing, uninstalling, and creating
skill patches.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from src.config import Config
from src.patch_installer import PatchInstaller
from src.patch_packager import PatchPackager


logger = logging.getLogger(__name__)
console = Console()


@click.group(name="patch")
def patch_commands():
    """Manage X-Skills patches.

    Patches are curated skill bundles for common use cases.
    """
    pass


@patch_commands.command("list")
def list_patches():
    """List all available patches.

    Shows all available skill patches with their skill counts
    and installation status.
    """
    installer = PatchInstaller()
    available = installer.list_available()
    installed = installer.list_installed()

    if not available:
        console.print("[yellow]No patches available.[/yellow]")
        console.print("[dim]Generate patches first with: python scripts/create_patches.py --all[/dim]")
        return

    # Create table
    table = Table(title="Available Patches", show_header=True, header_style="bold magenta")
    table.add_column("Patch ID", style="cyan", width=20)
    table.add_column("Name", width=25)
    table.add_column("Skills", width=8)
    table.add_column("Status", width=12)

    for patch_id in sorted(available):
        info = installer.get_patch_info(patch_id)
        if info:
            status = "[green]✓ Installed[/green]" if patch_id in installed else "[dim]Not installed[/dim]"
            table.add_row(
                patch_id,
                info["name"],
                str(info["skill_count"]),
                status
            )

    console.print(table)
    console.print(f"\n[green]{len(available)} patch(es) available[/green]")
    console.print(f"[cyan]{len(installed)} patch(es) installed[/cyan]")


@patch_commands.command("install")
@click.argument("patch_ids", nargs=-1, required=True)
@click.option("--force", "-f", is_flag=True, help="Force reinstall")
@click.option("--copy", is_flag=True, help="Copy files instead of symlinks")
def install_patch(patch_ids: tuple, force: bool, copy: bool):
    """Install one or more patches.

    Patch installs skills to ~/.claude/skills/ directory.

    \b
    Examples:
        /xskills patch install research-agent
        /xskills patch install research-agent web-dev-agent
        /xskills patch install research-agent --force
    """
    installer = PatchInstaller()

    results = {
        "success": [],
        "failed": [],
        "skipped": []
    }

    for patch_id in patch_ids:
        console.print(f"[cyan]Installing patch: {patch_id}[/cyan]")

        with console.status(f"[bold green]Installing {patch_id}..."):
            success = installer.install(patch_id, force=force, use_symlinks=not copy)

        if success:
            results["success"].append(patch_id)
            console.print(f"[green]✓ Installed {patch_id}[/green]")
        else:
            results["failed"].append(patch_id)
            console.print(f"[red]✗ Failed to install {patch_id}[/red]")

    # Summary
    console.print("\n" + "="*50)
    if results["success"]:
        console.print(f"[green]✓ Installed: {', '.join(results['success'])}[/green]")
    if results["failed"]:
        console.print(f"[red]✗ Failed: {', '.join(results['failed'])}[/red]")


@patch_commands.command("uninstall")
@click.argument("patch_ids", nargs=-1, required=True)
def uninstall_patch(patch_ids: tuple):
    """Uninstall one or more patches.

    \b
    Examples:
        /xskills patch uninstall research-agent
        /xskills patch uninstall research-agent web-dev-agent
    """
    installer = PatchInstaller()

    results = {
        "success": [],
        "failed": [],
        "not_found": []
    }

    for patch_id in patch_ids:
        console.print(f"[cyan]Uninstalling patch: {patch_id}[/cyan]")

        if patch_id not in installer.list_installed():
            results["not_found"].append(patch_id)
            console.print(f"[yellow]○ Patch '{patch_id}' is not installed[/yellow]")
            continue

        with console.status(f"[bold yellow]Uninstalling {patch_id}..."):
            success = installer.uninstall(patch_id)

        if success:
            results["success"].append(patch_id)
            console.print(f"[green]✓ Uninstalled {patch_id}[/green]")
        else:
            results["failed"].append(patch_id)
            console.print(f"[red]✗ Failed to uninstall {patch_id}[/red]")

    # Summary
    console.print("\n" + "="*50)
    if results["success"]:
        console.print(f"[green]✓ Uninstalled: {', '.join(results['success'])}[/green]")
    if results["not_found"]:
        console.print(f"[yellow]○ Not found: {', '.join(results['not_found'])}[/yellow]")
    if results["failed"]:
        console.print(f"[red]✗ Failed: {', '.join(results['failed'])}[/red]")


@patch_commands.command("info")
@click.argument("patch_id")
def patch_info(patch_id: str):
    """Show detailed information about a patch.

    \b
    Examples:
        /xskills patch info research-agent
    """
    installer = PatchInstaller()
    info = installer.get_patch_info(patch_id)

    if not info:
        console.print(f"[red]Patch not found: {patch_id}[/red]")
        console.print("[dim]Use '/xskills patch list' to see available patches[/dim]")
        return

    # Display patch info
    status_text = "[green]✓ Installed[/green]" if info["installed"] else "[dim]Not installed[/dim]"

    panel = Panel(
        f"""[bold cyan]Name:[/bold cyan] {info['name']}
[bold cyan]ID:[/bold cyan] {info['id']}
[bold cyan]Description:[/bold cyan] {info.get('description', 'N/A')}
[bold cyan]Version:[/bold cyan] {info['version']}
[bold cyan]Skills:[/bold cyan] {info['skill_count']}
[bold cyan]Status:[/bold cyan] {status_text}
[bold cyan]Generated:[/bold cyan] {info['generated_at']}""",
        title=f"Patch: {patch_id}",
        border_style="cyan"
    )

    console.print(panel)


@patch_commands.command("create")
@click.argument("patch_id")
@click.option("--name", "-n", required=True, help="Patch name")
@click.option("--description", "-d", help="Patch description")
@click.option("--skills", "-s", help="Comma-separated list of skill paths")
@click.option("--category", "-c", help="Filter by category")
@click.option("--max-skills", "-m", type=int, default=50, help="Maximum skills")
@click.option("--output", "-o", help="Output directory", default="custom-patches")
def create_patch(
    patch_id: str,
    name: str,
    description: str,
    skills: str,
    category: str,
    max_skills: int,
    output: str
):
    """Create a custom skill patch.

    \b
    Examples:
        /xskills patch create my-research --name "My Research" --category research
        /xskills patch create my-patch --name "Custom" --skills "skill1,skill2"
    """
    config = Config()
    packager = PatchPackager(config)

    console.print(f"[cyan]Creating custom patch: {patch_id}[/cyan]")

    # Parse skill list if provided
    skill_list = []
    if skills:
        skill_list = [s.strip() for s in skills.split(",")]

    # Create patch spec
    patch_spec = {
        "id": patch_id,
        "name": name,
        "description": description or f"Custom patch: {name}",
        "use_case": description or f"Custom use case: {name}",
        "categories": [category] if category else [],
        "subcategories": [],
        "tags": [],
        "exclude": [],
        "min_stars": None,
        "max_skills": max_skills,
        "required_skills": skill_list,
        "optional_skills": [],
        "dependencies": [],
        "version": "1.0.0"
    }

    # Generate patch
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # TODO: Implement custom patch generation
    console.print(f"[yellow]Custom patch creation - under development[/yellow]")
    console.print(f"[dim]Patch spec: {json.dumps(patch_spec, indent=2)}[/dim]")


@patch_commands.command("update")
@click.argument("patch_ids", nargs=-1)
def update_patch(patch_ids: tuple):
    """Update installed patches to latest version.

    If no patch IDs specified, updates all installed patches.

    \b
    Examples:
        /xskills patch update
        /xskills patch update research-agent
    """
    installer = PatchInstaller()

    if not patch_ids:
        # Update all
        console.print("[cyan]Updating all installed patches...[/cyan]")
        results = installer.update_all()

        for patch_id, success in results.items():
            status = "✓" if success else "✗"
            color = "green" if success else "red"
            console.print(f"[{color}]{status} {patch_id}[/{color}]")
    else:
        # Update specified
        for patch_id in patch_ids:
            console.print(f"[cyan]Updating {patch_id}...[/cyan]")
            success = installer.update(patch_id)
            status = "✓" if success else "✗"
            color = "green" if success else "red"
            console.print(f"[{color}]{status} {patch_id}[/{color}]")


__all__ = ["patch_commands"]
