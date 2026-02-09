"""X-Skills Claude Code Plugin

This plugin provides seamless integration between X-Skills and Claude Code.
Users can browse, install, and manage skill patches directly within Claude Code.

Installation:
    /plugin install xskills

Or via pip:
    pip install xskills-claude

Usage:
    /xskills patches list              # List available patches
    /xskills patch install research    # Install a patch
    /xskills browse                    # Browse all skills
    /xskills search research           # Search skills
"""

__version__ = "1.0.0"
__author__ = "SkillFlow"
__plugin_id__ = "xskills"

from src.claude_plugin.commands.patch import patch_commands
from src.claude_plugin.commands.skill import skill_commands


def register_commands(cli):
    """Register X-Skills commands with Claude Code CLI.

    Args:
        cli: Claude Code CLI instance
    """
    # Register patch commands
    cli.add_command(patch_commands)

    # Register skill commands
    cli.add_command(skill_commands)


def plugin_info():
    """Return plugin information for Claude Code.

    Returns:
        Dictionary with plugin metadata
    """
    return {
        "id": "xskills",
        "name": "X-Skills",
        "version": __version__,
        "description": "Access 9000+ AI-powered skills through curated patches",
        "author": "SkillFlow",
        "homepage": "https://github.com/tools-only/X-Skills",
        "commands": [
            {
                "name": "patches",
                "description": "List available patches",
                "usage": "/xskills patches list"
            },
            {
                "name": "patch",
                "description": "Install/uninstall patches",
                "usage": "/xskills patch install <patch-id>"
            },
            {
                "name": "browse",
                "description": "Browse all skills",
                "usage": "/xskills browse"
            },
            {
                "name": "search",
                "description": "Search skills",
                "usage": "/xskills search <query>"
            }
        ],
        "skills": [
            {
                "id": "xskills",
                "name": "X-Skills Manager",
                "description": "Manage X-Skills patches and browse skills",
                "file": "skills/xskills.md"
            }
        ]
    }


__all__ = [
    "register_commands",
    "plugin_info",
    "__version__",
]
