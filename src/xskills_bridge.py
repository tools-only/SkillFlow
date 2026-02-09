"""X-Skills Bridge - Integration layer for Claude Code plugin.

Provides the main interface between Claude Code's plugin system
and X-Skills functionality.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import Config
from src.patch_installer import PatchInstaller
from src.skill_browser import SkillBrowser
from src.custom_skill_editor import CustomSkillEditor


logger = logging.getLogger(__name__)


class XSkillsBridge:
    """Bridge between Claude Code plugin and X-Skills functionality.

    This class provides a unified interface for:
    - Patch management (install, uninstall, list)
    - Skill browsing and searching
    - Custom skill creation
    - Integration with Claude Code's skill system
    """

    def __init__(self, config: Optional[Config] = None):
        """Initialize the X-Skills Bridge.

        Args:
            config: Optional configuration object
        """
        self.config = config or Config()

        # Initialize components
        self.patch_installer = PatchInstaller(self.config)
        self.skill_browser = SkillBrowser(self.config)
        self.custom_editor = CustomSkillEditor(self.config)

        # Paths
        self.claude_skills_dir = Path.home() / ".claude" / "skills"
        self.xskills_dir = Path(self.config.get(
            "xskills.directory",
            "skillflow_repos/X-Skills"
        ))

    # === Patch Management ===

    def list_patches(self) -> List[Dict[str, Any]]:
        """List all available patches.

        Returns:
            List of patch information dictionaries
        """
        available = self.patch_installer.list_available()
        installed = self.patch_installer.list_installed()

        patches = []
        for patch_id in sorted(available):
            info = self.patch_installer.get_patch_info(patch_id)
            if info:
                patches.append({
                    "id": patch_id,
                    **info
                })

        return patches

    def install_patch(
        self,
        patch_id: str,
        force: bool = False,
        use_symlinks: bool = True
    ) -> Dict[str, Any]:
        """Install a patch to Claude Code.

        Args:
            patch_id: Patch identifier
            force: Force reinstall
            use_symlinks: Use symlinks instead of copying

        Returns:
            Result dictionary with status and message
        """
        success = self.patch_installer.install(patch_id, force=force, use_symlinks=use_symlinks)

        return {
            "success": success,
            "patch_id": patch_id,
            "message": f"Patch '{patch_id}' {'installed' if success else 'failed to install'}"
        }

    def uninstall_patch(self, patch_id: str) -> Dict[str, Any]:
        """Uninstall a patch from Claude Code.

        Args:
            patch_id: Patch identifier

        Returns:
            Result dictionary with status and message
        """
        success = self.patch_installer.uninstall(patch_id)

        return {
            "success": success,
            "patch_id": patch_id,
            "message": f"Patch '{patch_id}' {'uninstalled' if success else 'failed to uninstall'}"
        }

    def get_patch_info(self, patch_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a patch.

        Args:
            patch_id: Patch identifier

        Returns:
            Patch information dictionary or None
        """
        return self.patch_installer.get_patch_info(patch_id)

    # === Skill Browsing ===

    def list_skills(
        self,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List skills from X-Skills repository.

        Args:
            category: Filter by category
            limit: Maximum results

        Returns:
            List of skill information dictionaries
        """
        return self.skill_browser.list_skills(category=category, limit=limit)

    def search_skills(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search skills by keyword.

        Args:
            query: Search query
            category: Filter by category
            limit: Maximum results

        Returns:
            List of matching skills with scores
        """
        return self.skill_browser.search_skills(query, category=category, limit=limit)

    def get_skill_info(self, skill_path: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a skill.

        Args:
            skill_path: Skill path (e.g., "research/094-searching_f25e7adf")

        Returns:
            Skill information dictionary or None
        """
        return self.skill_browser.get_skill_info(skill_path)

    def get_skill_content(self, skill_path: str) -> Optional[str]:
        """Get the full content of a skill.

        Args:
            skill_path: Skill path

        Returns:
            Skill content string or None
        """
        return self.skill_browser.get_skill_content(skill_path)

    # === Categories ===

    def list_categories(self) -> List[str]:
        """List all available skill categories.

        Returns:
            List of category names
        """
        return self.skill_browser.list_categories()

    def get_category_stats(self) -> Dict[str, int]:
        """Get skill count per category.

        Returns:
            Dictionary mapping category to count
        """
        return self.skill_browser.get_category_stats()

    # === Custom Skills ===

    def create_custom_skill(
        self,
        name: str,
        category: str,
        description: Optional[str] = None,
        template: Optional[str] = None
    ) -> str:
        """Create a custom skill.

        Args:
            name: Skill name
            category: Skill category
            description: Optional description
            template: Optional template type

        Returns:
            Created skill content
        """
        if template:
            return self.custom_editor.create_from_template(template, name, description)
        else:
            return self.custom_editor.create_basic_skill(name, category, description)

    def add_skill_to_patch(self, skill_path: str, patch_id: str) -> bool:
        """Add a skill to a custom patch.

        Args:
            skill_path: Path to skill
            patch_id: Custom patch ID

        Returns:
            True if successful
        """
        return self.custom_editor.add_skill_to_patch(skill_path, patch_id)

    def list_custom_patches(self) -> Dict[str, Any]:
        """List all custom patches.

        Returns:
            Dictionary of custom patches
        """
        return self.custom_editor.list_custom_patches()

    def export_custom_patch(self, patch_id: str, output_dir: Optional[Path] = None) -> bool:
        """Export a custom patch.

        Args:
            patch_id: Patch identifier
            output_dir: Output directory

        Returns:
            True if successful
        """
        return self.custom_editor.export_patch(patch_id, output_dir)

    # === Status & Info ===

    def get_status(self) -> Dict[str, Any]:
        """Get X-Skills system status.

        Returns:
            Status dictionary with system information
        """
        installed_patches = self.patch_installer.list_installed()

        # Get skill counts
        category_stats = self.get_category_stats()
        total_skills = sum(category_stats.values())

        return {
            "xskills_version": "1.0.0",
            "total_skills": total_skills,
            "total_categories": len(category_stats),
            "available_patches": len(self.patch_installer.list_available()),
            "installed_patches": len(installed_patches),
            "custom_patches": len(self.custom_editor.list_custom_patches()),
            "claude_skills_dir": str(self.claude_skills_dir),
            "claude_skills_exists": self.claude_skills_dir.exists(),
            "xskills_dir": str(self.xskills_dir),
            "xskills_exists": self.xskills_dir.exists(),
        }

    def get_summary(self) -> str:
        """Get a human-readable summary of X-Skills status.

        Returns:
            Formatted summary string
        """
        status = self.get_status()

        lines = [
            "X-Skills Plugin Status",
            "=" * 40,
            f"Version: {status['xskills_version']}",
            f"Total Skills: {status['total_skills']}",
            f"Categories: {status['total_categories']}",
            f"Available Patches: {status['available_patches']}",
            f"Installed Patches: {status['installed_patches']}",
            f"Custom Patches: {status['custom_patches']}",
        ]

        return "\n".join(lines)


__all__ = ["XSkillsBridge"]
