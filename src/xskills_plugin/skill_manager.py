"""
Skill Manager for X-Skills Plugin

Provides a unified API integrating the indexer, loader, linker, and config manager.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set

from .config_manager import ConfigManager, XSkillsConfig
from .linker import Linker
from .skill_indexer import SkillIndex, SkillMetadata
from .skill_loader import SkillLoader


class SkillManager:
    """
    Unified manager for X-Skills plugin.

    Integrates all components to provide a simple API for:
    - Listing and searching skills
    - Enabling/disabling skills
    - Applying configuration
    - Syncing symbolic links
    """

    def __init__(
        self,
        xskills_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
        link_target: Optional[Path] = None,
    ):
        """
        Initialize the skill manager.

        Args:
            xskills_path: Path to the X-Skills repository
            config_path: Path to the configuration file
            link_target: Path where symlinks will be created
        """
        project_root = Path(__file__).parent.parent.parent

        if xskills_path is None:
            xskills_path = project_root / "skillflow_repos" / "X-Skills"
        if config_path is None:
            config_path = project_root / "config" / "xskills_config.yaml"
        if link_target is None:
            link_target = project_root / ".claude" / "skills" / "xskills"

        self.xskills_path = Path(xskills_path)
        self.config_path = Path(config_path)
        self.link_target = Path(link_target)

        # Initialize components
        self.index = SkillIndex(self.xskills_path)
        self.loader = SkillLoader(self.xskills_path)
        self.config_manager = ConfigManager(self.config_path)
        self.linker = Linker(self.link_target, self.xskills_path)

        self._config_loaded = False

    def _ensure_loaded(self) -> None:
        """Ensure index and configuration are loaded."""
        if not self.index._loaded:
            self.index.load()
        if not self._config_loaded:
            self.config_manager.load()
            self._config_loaded = True

    # === Query Methods ===

    def list_skills(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        enabled_only: bool = False,
    ) -> List[SkillMetadata]:
        """
        List skills with optional filtering.

        Args:
            category: Filter by category
            tags: Filter by tags (must match all)
            enabled_only: Only show enabled skills

        Returns:
            List of matching skill metadata
        """
        self._ensure_loaded()

        skills = self.index.list_skills(category=category, tags=tags)

        if enabled_only:
            enabled = self.get_enabled_skills()
            skills = [s for s in skills if s.name in enabled]

        return skills

    def search_skills(self, query: str) -> List[SkillMetadata]:
        """
        Search for skills by query string.

        Args:
            query: Search query for name, display_name, or description

        Returns:
            List of matching skill metadata
        """
        self._ensure_loaded()
        return self.index.list_skills(search_query=query)

    def get_skill(self, name: str) -> Optional[SkillMetadata]:
        """Get metadata for a specific skill."""
        self._ensure_loaded()
        return self.index.get_skill(name)

    def list_categories(self) -> List[str]:
        """Get list of all available categories."""
        self._ensure_loaded()
        return self.index.list_categories()

    def list_tags(self) -> List[str]:
        """Get list of all available tags."""
        self._ensure_loaded()
        return self.index.list_tags()

    # === Content Methods ===

    def load_skill(self, name: str) -> Optional[str]:
        """Load a skill's content by name."""
        return self.loader.load_skill(name)

    def load_skill_with_metadata(self, name: str) -> Optional[Dict]:
        """Load a skill with its metadata separated."""
        return self.loader.load_skill_with_metadata(name)

    # === Enabled State Methods ===

    def get_enabled_skills(self) -> Set[str]:
        """
        Get the set of currently enabled skill names.

        Returns:
            Set of enabled skill names
        """
        self._ensure_loaded()
        return self.config_manager.get_enabled_skills(
            list(self.index.skills.keys()),
            self.index.by_category,
            self.index.by_tags,
        )

    def get_linked_skills(self) -> List[str]:
        """Get list of currently linked (active) skill names."""
        return self.linker.get_linked_skills()

    # === Enable/Disable Methods ===

    def enable_skills(self, names: List[str]) -> None:
        """
        Enable specific skills by name.

        Args:
            names: List of skill names to enable
        """
        self._ensure_loaded()

        for name in names:
            if name in self.index.skills:
                self.config_manager.add_skill_by_name(name)

        self.config_manager.save()

    def disable_skills(self, names: List[str]) -> None:
        """
        Disable specific skills by name.

        Args:
            names: List of skill names to disable
        """
        self._ensure_loaded()

        for name in names:
            self.config_manager.remove_skill_by_name(name)

        self.config_manager.save()

    def enable_category(self, category: str, exclude: Optional[List[str]] = None) -> None:
        """
        Enable all skills in a category.

        Args:
            category: Category name to enable
            exclude: Optional list of skill names to exclude
        """
        self._ensure_loaded()
        self.config_manager.add_category(category, exclude)
        self.config_manager.save()

    def disable_category(self, category: str) -> None:
        """Disable all skills in a category."""
        self._ensure_loaded()
        self.config_manager.remove_category(category)
        self.config_manager.save()

    def enable_tag(self, tag: str) -> None:
        """Enable all skills with a specific tag."""
        self._ensure_loaded()
        self.config_manager.add_tag(tag)
        self.config_manager.save()

    def disable_tag(self, tag: str) -> None:
        """Disable all skills with a specific tag."""
        self._ensure_loaded()
        self.config_manager.remove_tag(tag)
        self.config_manager.save()

    def clear_all_enabled(self) -> None:
        """Clear all enabled skills."""
        self._ensure_loaded()
        self.config_manager.clear_all()
        self.config_manager.save()

    # === Sync Methods ===

    def sync(self, dry_run: bool = False) -> Dict[str, List[str]]:
        """
        Synchronize symbolic links to match configuration.

        Args:
            dry_run: If True, only return what would be done

        Returns:
            Dict with 'created', 'updated', 'removed', 'failed' lists
        """
        self._ensure_loaded()

        enabled = self.get_enabled_skills()
        link_strategy = self.config_manager.config.settings.link_strategy

        if dry_run:
            # Calculate what would change
            current = set(self.linker.get_linked_skills())
            enabled_set = set(enabled)

            return {
                "created": sorted(enabled_set - current),
                "updated": [],
                "removed": sorted(current - enabled_set),
                "failed": [],
            }

        return self.linker.sync_links(enabled, strategy=link_strategy)

    def apply_config(self, config_path: Optional[Path] = None) -> Dict[str, List[str]]:
        """
        Apply configuration from a file and sync links.

        Args:
            config_path: Path to config file. If None, uses default.

        Returns:
            Dict with 'created', 'updated', 'removed', 'failed' lists
        """
        if config_path:
            self.config_path = Path(config_path)
            self.config_manager = ConfigManager(self.config_path)

        # Reload and sync
        self._config_loaded = False
        return self.sync()

    # === Diagnostic Methods ===

    def check_broken_links(self) -> List[str]:
        """Check for broken symbolic links."""
        return self.linker.check_broken_links()

    def get_status(self) -> Dict[str, any]:
        """
        Get overall status of the plugin.

        Returns:
            Dict with status information
        """
        self._ensure_loaded()

        enabled = self.get_enabled_skills()
        linked = self.linker.get_linked_skills()
        broken = self.linker.check_broken_links()

        return {
            "total_skills": self.index.count(),
            "enabled_count": len(enabled),
            "linked_count": len(linked),
            "broken_links": len(broken),
            "categories": len(self.index.by_category),
            "tags": len(self.index.by_tags),
            "config_path": str(self.config_path),
            "config_exists": self.config_path.exists(),
            "link_target": str(self.link_target),
            "link_target_exists": self.link_target.exists(),
        }


def get_default_manager() -> SkillManager:
    """
    Get the default skill manager instance.

    Returns:
        A SkillManager instance with default paths.
    """
    return SkillManager()
