"""Skill browsing and management commands for X-Skills Claude Code plugin.

Provides commands for browsing, searching, and managing individual skills
from the X-Skills repository.
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
from rich.prompt import Prompt
from rich.syntax import Syntax

from src.config import Config


logger = logging.getLogger(__name__)
console = Console()


@click.group(name="skill")
def skill_commands():
    """Browse and manage X-Skills.

    Access 9000+ skills from the X-Skills repository.
    """
    pass


@skill_commands.command("browse")
@click.option("--category", "-c", help="Filter by category")
@click.option("--limit", "-l", type=int, default=50, help="Maximum results")
@click.option("--installed", is_flag=True, help="Show only installed skills")
def browse_skills(category: Optional[str], limit: int, installed: bool):
    """Browse skills from X-Skills repository.

    \b
    Examples:
        /xskills skill browse
        /xskills skill browse --category research
        /xskills skill browse --limit 100
    """
    from src.skill_browser import SkillBrowser

    browser = SkillBrowser()

    if installed:
        skills = browser.get_installed_skills()
    else:
        skills = browser.list_skills(category=category, limit=limit)

    if not skills:
        console.print("[yellow]No skills found[/yellow]")
        return

    # Display skills
    table = Table(title=f"Skills ({len(skills)} shown)", show_header=True, header_style="bold magenta")
    table.add_column("Path", style="cyan", width=40)
    table.add_column("Name", width=30)
    table.add_column("Category", width=15)
    table.add_column("Tags", width=20)

    for skill in skills[:limit]:
        tags = ", ".join(skill.get("tags", [])[:3])
        table.add_row(
            skill["path"],
            skill.get("name", "N/A")[:28],
            skill.get("category", "N/A"),
            tags
        )

    console.print(table)


@skill_commands.command("search")
@click.argument("query")
@click.option("--category", "-c", help="Filter by category")
@click.option("--limit", "-l", type=int, default=20, help="Maximum results")
def search_skills(query: str, category: Optional[str], limit: int):
    """Search skills by keyword.

    \b
    Examples:
        /xskills skill search research
        /xskills skill search "web development" --category development
        /xskills skill search citation --limit 10
    """
    from src.skill_browser import SkillBrowser

    browser = SkillBrowser()
    results = browser.search_skills(query, category=category, limit=limit)

    if not results:
        console.print(f"[yellow]No skills found matching '{query}'[/yellow]")
        return

    # Display results
    table = Table(title=f"Search Results: '{query}'", show_header=True, header_style="bold magenta")
    table.add_column("Path", style="cyan", width=35)
    table.add_column("Name", width=25)
    table.add_column("Description", width=40)
    table.add_column("Score", width=8)

    for skill in results:
        score = skill.get("score", 0)
        score_color = "green" if score > 70 else "yellow" if score > 40 else "red"

        table.add_row(
            skill["path"],
            skill.get("name", "N/A"),
            skill.get("description", "N/A")[:38],
            f"[{score_color}]{score}[/{score_color}]"
        )

    console.print(table)
    console.print(f"\n[green]Found {len(results)} skill(s)[/green]")


@skill_commands.command("info")
@click.argument("skill_path")
def skill_info(skill_path: str):
    """Show detailed information about a skill.

    \b
    Examples:
        /xskills skill info research/094-searching_f25e7adf
        /xskills skill info development/264-quickstart_666d3de7
    """
    from src.skill_browser import SkillBrowser

    browser = SkillBrowser()
    info = browser.get_skill_info(skill_path)

    if not info:
        console.print(f"[red]Skill not found: {skill_path}[/red]")
        console.print("[dim]Use '/xskills skill search' to find skills[/dim]")
        return

    # Display skill info
    tags = ", ".join(info.get("tags", []))

    panel = Panel(
        f"""[bold cyan]Name:[/bold cyan] {info.get('display_name', 'N/A')}
[bold cyan]Path:[/bold cyan] {skill_path}
[bold cyan]Category:[/bold cyan] {info.get('category', 'N/A')}
[bold cyan]Source:[/bold cyan] {info.get('source', 'N/A')}
[bold cyan]Tags:[/bold cyan] {tags if tags else 'N/A'}
[bold cyan]Description:[/bold cyan]

{info.get('description', 'No description available')}""",
        title=f"Skill: {info.get('display_name', skill_path)}",
        border_style="cyan"
    )

    console.print(panel)


@skill_commands.command("view")
@click.argument("skill_path")
def view_skill(skill_path: str):
    """View the full content of a skill.

    \b
    Examples:
        /xskills skill view research/094-searching_f25e7adf
    """
    from src.skill_browser import SkillBrowser

    browser = SkillBrowser()
    content = browser.get_skill_content(skill_path)

    if not content:
        console.print(f"[red]Skill not found: {skill_path}[/red]")
        return

    # Display skill content with syntax highlighting
    syntax = Syntax(content, "markdown", theme="monokai", line_numbers=True)
    console.print(syntax)


@skill_commands.command("create")
@click.argument("skill_name")
@click.option("--category", "-c", required=True, help="Skill category")
@click.option("--description", "-d", help="Skill description")
@click.option("--template", "-t", help="Use a template", is_flag=True)
@click.option("--output", "-o", help="Output file", default="custom-skills")
def create_skill(skill_name: str, category: str, description: str, template: bool, output: str):
    """Create a custom skill.

    \b
    Examples:
        /xskills skill create my-research-skill --category research --template
        /xskills skill create my-skill --category development --description "My custom skill"
    """
    from src.custom_skill_editor import CustomSkillEditor

    editor = CustomSkillEditor()

    console.print(f"[cyan]Creating custom skill: {skill_name}[/cyan]")

    if template:
        # Create from template
        template_type = category if category in editor.get_available_templates() else "basic"
        content = editor.create_from_template(template_type, skill_name, description)
    else:
        # Create basic skill
        content = editor.create_basic_skill(skill_name, category, description)

    # Save skill
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{skill_name}.md"
    output_file.write_text(content)

    console.print(f"[green]✓ Created skill: {output_file}[/green]")
    console.print(f"[dim]You can now edit this file and use it with Claude Code[/dim]")


@skill_commands.command("add")
@click.argument("skill_path")
@click.option("--patch", "-p", required=True, help="Target patch ID")
def add_to_patch(skill_path: str, patch: str):
    """Add a skill to a custom patch.

    \b
    Examples:
        /xskills skill add research/094-searching_f25e7adf --patch my-custom-patch
    """
    from src.custom_skill_editor import CustomSkillEditor

    editor = CustomSkillEditor()

    success = editor.add_skill_to_patch(skill_path, patch)

    if success:
        console.print(f"[green]✓ Added {skill_path} to patch '{patch}'[/green]")
    else:
        console.print(f"[red]✗ Failed to add skill to patch[/red]")


# Also add standalone commands at the top level
@click.command(name="browse")
@click.option("--category", "-c", help="Filter by category")
@click.option("--limit", "-l", type=int, default=50, help="Maximum results")
@click.option("--installed", is_flag=True, help="Show only installed skills")
@click.pass_context
def browse_command(ctx, category: Optional[str], limit: int, installed: bool):
    """Browse all skills from X-Skills.

    \b
    Examples:
        /xskills browse
        /xskills browse --category research
        /xskills browse --limit 100
    """
    # Forward to the actual command
    ctx.forward(browse_skills)


@click.command(name="search")
@click.argument("query")
@click.option("--category", "-c", help="Filter by category")
@click.option("--limit", "-l", type=int, default=20, help="Maximum results")
@click.pass_context
def search_command(ctx, query: str, category: Optional[str], limit: int):
    """Search skills by keyword.

    \b
    Examples:
        /xskills search research
        /xskills search "web development" --category development
    """
    # Forward to the actual command
    ctx.forward(search_skills)


__all__ = ["skill_commands", "browse_command", "search_command"]
