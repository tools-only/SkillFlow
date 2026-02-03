#!/usr/bin/env python3
"""
X-Skills CLI

Command-line interface for managing X-Skills plugin.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import print as rprint

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None

from xskills_plugin import SkillManager, SkillMetadata


class XSkillsCLI:
    """Command-line interface for X-Skills management."""

    def __init__(self):
        self.manager = SkillManager()
        if RICH_AVAILABLE:
            self.console = Console()
        else:
            self.console = None

    def _print(self, *args, **kwargs):
        """Print with rich if available."""
        if RICH_AVAILABLE:
            self.console.print(*args, **kwargs)
        else:
            print(*args)

    def _print_table(self, columns: list, rows: list, title: Optional[str] = None):
        """Print a table with rich if available."""
        if RICH_AVAILABLE:
            table = Table(title=title)
            for col in columns:
                table.add_column(col)
            for row in rows:
                table.add_row(*[str(v) for v in row])
            self.console.print(table)
        else:
            if title:
                print(f"\n{title}")
                print("=" * len(title))
            # Print header
            print(" | ".join(columns))
            print("-" * len(" | ".join(columns)))
            # Print rows
            for row in rows:
                print(" | ".join(str(v) for v in row))

    def cmd_list(self, args) -> int:
        """List available skills."""
        self.manager._ensure_loaded()

        if args.category:
            skills = self.manager.list_skills(category=args.category, enabled_only=args.enabled)
        elif args.enabled:
            skills = self.manager.list_skills(enabled_only=True)
        else:
            skills = self.manager.list_skills()

        if args.json:
            data = [
                {
                    "name": s.name,
                    "display_name": s.display_name,
                    "category": s.category,
                    "tags": s.tags,
                    "description": s.description[:100] + "..." if len(s.description) > 100 else s.description,
                }
                for s in skills
            ]
            print(json.dumps(data, indent=2))
        else:
            rows = []
            for s in skills[:args.limit]:
                tags_str = ", ".join(s.tags[:3]) if s.tags else ""
                desc = s.description[:50] + "..." if len(s.description) > 50 else s.description
                rows.append([s.name, s.display_name, s.category, tags_str, desc])

            self._print_table(
                ["Name", "Display", "Category", "Tags", "Description"],
                rows,
                title=f"Skills ({len(skills)} total)"
            )

        return 0

    def cmd_search(self, args) -> int:
        """Search for skills."""
        self.manager._ensure_loaded()

        skills = self.manager.search_skills(args.query)

        if not skills:
            self._print(f"[yellow]No skills found matching '{args.query}'[/yellow]")
            return 1

        rows = []
        for s in skills[:args.limit]:
            tags_str = ", ".join(s.tags[:3]) if s.tags else ""
            rows.append([s.name, s.display_name, s.category, tags_str])

        self._print_table(
            ["Name", "Display", "Category", "Tags"],
            rows,
            title=f"Search results for '{args.query}' ({len(skills)} found)"
        )

        return 0

    def cmd_categories(self, args) -> int:
        """List all categories."""
        self.manager._ensure_loaded()

        categories = self.manager.list_categories()

        if args.json:
            print(json.dumps(categories, indent=2))
        else:
            for cat in categories:
                count = len(self.manager.list_skills(category=cat))
                print(f"  {cat}: {count} skills")

        return 0

    def cmd_tags(self, args) -> int:
        """List all tags."""
        self.manager._ensure_loaded()

        tags = self.manager.list_tags()

        if args.json:
            print(json.dumps(tags, indent=2))
        else:
            print("  " + "\n  ".join(tags))

        return 0

    def cmd_enable(self, args) -> int:
        """Enable skills."""
        self.manager._ensure_loaded()

        if args.interactive:
            return self._interactive_enable(args)

        if args.category:
            # Parse exclusions if any
            exclude = args.exclude or []
            self.manager.enable_category(args.category, exclude if exclude else None)
            self._print(f"[green]Enabled category: {args.category}[/green]")
            if exclude:
                self._print(f"[dim]Excluded: {', '.join(exclude)}[/dim]")
        elif args.tag:
            self.manager.enable_tag(args.tag)
            self._print(f"[green]Enabled tag: {args.tag}[/green]")
        elif args.skills:
            for skill in args.skills:
                if self.manager.get_skill(skill):
                    self.manager.config_manager.add_skill_by_name(skill)
                else:
                    self._print(f"[yellow]Skill not found: {skill}[/yellow]")
            self.manager.config_manager.save()
            self._print(f"[green]Enabled {len(args.skills)} skill(s)[/green]")
        else:
            self._print("[yellow]No skills specified. Use --skill, --category, --tag, or --interactive[/yellow]")
            return 1

        if args.sync:
            result = self.manager.sync()
            self._print_sync_result(result)

        return 0

    def cmd_disable(self, args) -> int:
        """Disable skills."""
        self.manager._ensure_loaded()

        if args.category:
            self.manager.disable_category(args.category)
            self._print(f"[green]Disabled category: {args.category}[/green]")
        elif args.tag:
            self.manager.disable_tag(args.tag)
            self._print(f"[green]Disabled tag: {args.tag}[/green]")
        elif args.skills:
            for skill in args.skills:
                self.manager.config_manager.remove_skill_by_name(skill)
            self.manager.config_manager.save()
            self._print(f"[green]Disabled {len(args.skills)} skill(s)[/green]")
        else:
            self._print("[yellow]No skills specified. Use --skill, --category, or --tag[/yellow]")
            return 1

        if args.sync:
            result = self.manager.sync()
            self._print_sync_result(result)

        return 0

    def cmd_sync(self, args) -> int:
        """Sync configuration to symbolic links."""
        result = self.manager.sync(dry_run=args.dry_run)

        if args.dry_run:
            self._print("[dim]Dry run - no changes made[/dim]")

        self._print_sync_result(result)
        return 0

    def cmd_status(self, args) -> int:
        """Show plugin status."""
        status = self.manager.get_status()

        if args.json:
            print(json.dumps(status, indent=2))
        else:
            self._print(Panel.fit(
                f"[bold]X-Skills Plugin Status[/bold]\n\n"
                f"Total Skills: {status['total_skills']}\n"
                f"Enabled: {status['enabled_count']}\n"
                f"Linked: {status['linked_count']}\n"
                f"Broken Links: {status['broken_links']}\n"
                f"Categories: {status['categories']}\n"
                f"Tags: {status['tags']}\n\n"
                f"Config: {status['config_path']}\n"
                f"Link Target: {status['link_target']}",
                title="Status"
            ))

            if status['broken_links'] > 0:
                broken = self.manager.check_broken_links()
                self._print(f"\n[yellow]Broken links:[/yellow] {', '.join(broken)}")

        return 0

    def cmd_config(self, args) -> int:
        """Manage configuration."""
        if args.init:
            from xskills_plugin.config_manager import ConfigManager
            ConfigManager.create_default_config(self.manager.config_path)
            self._print(f"[green]Created config template at: {self.manager.config_path}[/green]")
            return 0

        if args.show:
            self.manager._ensure_loaded()
            config_data = self.manager.config_manager._config_to_dict(
                self.manager.config_manager.config
            )
            print(json.dumps(config_data, indent=2))
            return 0

        if args.edit:
            import os
            import subprocess
            editor = os.environ.get("EDITOR", "vi")
            subprocess.call([editor, str(self.manager.config_path)])
            return 0

        self._print("Use --init to create config, --show to view, or --edit to edit")
        return 0

    def _print_sync_result(self, result: dict) -> None:
        """Print sync operation results."""
        if result["created"]:
            self._print(f"[green]Created: {len(result['created'])} link(s)[/green]")
        if result["updated"]:
            self._print(f"[blue]Updated: {len(result['updated'])} link(s)[/blue]")
        if result["removed"]:
            self._print(f"[red]Removed: {len(result['removed'])} link(s)[/red]")
        if result["failed"]:
            self._print(f"[yellow]Failed: {', '.join(result['failed'])}[/yellow]")

    def _interactive_enable(self, args) -> int:
        """Interactive mode for enabling skills."""
        try:
            import questionary
        except ImportError:
            self._print("[yellow]questionary package required for interactive mode[/yellow]")
            self._print("Install with: pip install questionary")
            return 1

        self.manager._ensure_loaded()

        # Step 1: Choose selection method
        method = questionary.select(
            "How would you like to select skills?",
            choices=[
                "By Category",
                "By Tag",
                "Search",
                "Browse All",
            ]
        ).ask()

        if method == "By Category":
            categories = self.manager.list_categories()
            category = questionary.select(
                "Select a category:",
                choices=categories + ["[Cancel]"]
            ).ask()

            if category and category != "[Cancel]":
                skills = self.manager.list_skills(category=category)
                selections = questionary.checkbox(
                    f"Select skills from {category}:",
                    choices=[s.display_name for s in skills] + ["[Select All]"]
                ).ask()

                if "[Select All]" in selections:
                    selections = [s.display_name for s in skills]

                # Map display names back to skill names
                name_map = {s.display_name: s.name for s in skills}
                selected_names = [name_map.get(s, s) for s in selections if s != "[Select All]"]

                self.manager.enable_skills(selected_names)

        elif method == "By Tag":
            tags = self.manager.list_tags()
            tag = questionary.select(
                "Select a tag:",
                choices=tags + ["[Cancel]"]
            ).ask()

            if tag and tag != "[Cancel]":
                skills = [s for s in self.manager.list_skills() if tag in s.tags]
                selections = questionary.checkbox(
                    f"Select skills with tag '{tag}':",
                    choices=[s.display_name for s in skills] + ["[Select All]"]
                ).ask()

                if "[Select All]" in selections:
                    selections = [s.display_name for s in skills]

                name_map = {s.display_name: s.name for s in skills}
                selected_names = [name_map.get(s, s) for s in selections if s != "[Select All]"]

                self.manager.enable_skills(selected_names)

        elif method == "Search":
            query = questionary.text("Enter search query:").ask()
            if query:
                skills = self.manager.search_skills(query)
                if not skills:
                    self._print("[yellow]No skills found[/yellow]")
                    return 0

                selections = questionary.checkbox(
                    f"Select matching skills:",
                    choices=[s.display_name for s in skills] + ["[Select All]"]
                ).ask()

                if "[Select All]" in selections:
                    selections = [s.display_name for s in skills]

                name_map = {s.display_name: s.name for s in skills}
                selected_names = [name_map.get(s, s) for s in selections if s != "[Select All]"]

                self.manager.enable_skills(selected_names)

        elif method == "Browse All":
            skills = self.manager.list_skills()
            self._print(f"Found {len(skills)} skills. Showing first 20...")

            selections = questionary.checkbox(
                "Select skills:",
                choices=[s.display_name for s in skills[:20]] + ["[Cancel]"]
            ).ask()

            if selections and "[Cancel]" not in selections:
                name_map = {s.display_name: s.name for s in skills[:20]}
                selected_names = [name_map.get(s, s) for s in selections if s != "[Cancel]"]
                self.manager.enable_skills(selected_names)

        # Ask if user wants to sync
        sync = questionary.confirm("Sync links now?", default=True).ask()
        if sync:
            result = self.manager.sync()
            self._print_sync_result(result)

        return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="xskills",
        description="X-Skills Plugin Manager for Claude Code"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List skills")
    list_parser.add_argument("--category", "-c", help="Filter by category")
    list_parser.add_argument("--enabled", "-e", action="store_true", help="Show only enabled skills")
    list_parser.add_argument("--limit", "-l", type=int, default=50, help="Limit number of results")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search for skills")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", "-l", type=int, default=20, help="Limit number of results")

    # Categories command
    cat_parser = subparsers.add_parser("categories", help="List all categories")
    cat_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Tags command
    tag_parser = subparsers.add_parser("tags", help="List all tags")
    tag_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Enable command
    enable_parser = subparsers.add_parser("enable", help="Enable skills")
    enable_parser.add_argument("skills", nargs="*", help="Skill names to enable")
    enable_parser.add_argument("--category", "-c", help="Enable all skills in category")
    enable_parser.add_argument("--tag", "-t", help="Enable all skills with tag")
    enable_parser.add_argument("--exclude", nargs="*", help="Skills to exclude when using --category")
    enable_parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    enable_parser.add_argument("--sync", "-s", action="store_true", help="Sync after enabling")

    # Disable command
    disable_parser = subparsers.add_parser("disable", help="Disable skills")
    disable_parser.add_argument("skills", nargs="*", help="Skill names to disable")
    disable_parser.add_argument("--category", "-c", help="Disable all skills in category")
    disable_parser.add_argument("--tag", "-t", help="Disable all skills with tag")
    disable_parser.add_argument("--sync", "-s", action="store_true", help="Sync after disabling")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Sync configuration to symbolic links")
    sync_parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show plugin status")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Config command
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_parser.add_argument("--init", action="store_true", help="Create default config")
    config_parser.add_argument("--show", action="store_true", help="Show current config")
    config_parser.add_argument("--edit", action="store_true", help="Edit config in editor")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    cli = XSkillsCLI()
    command_method = getattr(cli, f"cmd_{args.command}", None)
    if command_method:
        return command_method(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
