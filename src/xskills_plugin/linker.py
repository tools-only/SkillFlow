"""
Linker for X-Skills Plugin

Manages symbolic links from .claude/skills/xskills/ to the X-Skills repository.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set

from .skill_indexer import SkillIndex, SkillMetadata


class Linker:
    """
    Manages symbolic links for enabled X-Skills.

    Creates, updates, and removes symlinks in the target directory
    pointing to skill files in the X-Skills repository.
    """

    def __init__(
        self,
        link_target: Optional[Path] = None,
        xskills_path: Optional[Path] = None,
    ):
        """
        Initialize the linker.

        Args:
            link_target: Directory where symlinks will be created.
                        Defaults to .claude/skills/xskills/
            xskills_path: Path to the X-Skills repository.
        """
        if link_target is None:
            project_root = Path(__file__).parent.parent.parent
            link_target = project_root / ".claude" / "skills" / "xskills"

        if xskills_path is None:
            project_root = Path(__file__).parent.parent.parent
            xskills_path = project_root / "skillflow_repos" / "X-Skills"

        self.link_target = Path(link_target)
        self.xskills_path = Path(xskills_path)
        self.index = SkillIndex(xskills_path)

    def _get_skill_source_path(self, skill_name: str) -> Optional[Path]:
        """
        Get the source path for a skill's skill.md file.

        Args:
            skill_name: Name of the skill

        Returns:
            Path to the skill.md file, or None if not found
        """
        metadata = self.index.get_skill(skill_name)
        if not metadata:
            return None

        source_path = self.xskills_path / metadata.local_path / "skill.md"
        if not source_path.exists():
            return None

        return source_path

    def _get_link_path(self, skill_name: str) -> Path:
        """
        Get the path where a skill's symlink should be created.

        Args:
            skill_name: Name of the skill

        Returns:
            Path where the symlink should be created
        """
        # Use skill.md as the link name for Claude Code compatibility
        return self.link_target / skill_name / "skill.md"

    def link_skill(self, skill_name: str) -> bool:
        """
        Create a symlink for a single skill.

        Args:
            skill_name: Name of the skill to link

        Returns:
            True if successful, False otherwise
        """
        source_path = self._get_skill_source_path(skill_name)
        if not source_path:
            return False

        link_path = self._get_link_path(skill_name)

        # Create parent directory
        link_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing link if present
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()

        try:
            # Create relative symlink for portability
            relative_source = os.path.relpath(source_path, link_path.parent)
            os.symlink(relative_source, link_path)
            return True
        except (OSError, NotImplementedError):
            # Fall back to absolute link if relative fails
            try:
                os.symlink(source_path, link_path)
                return True
            except OSError:
                return False

    def unlink_skill(self, skill_name: str) -> bool:
        """
        Remove a symlink for a single skill.

        Args:
            skill_name: Name of the skill to unlink

        Returns:
            True if successful (or link didn't exist), False otherwise
        """
        link_path = self._get_link_path(skill_name)

        if link_path.is_symlink() or link_path.exists():
            try:
                # Also remove the parent directory if empty
                parent = link_path.parent
                link_path.unlink()
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                return True
            except OSError:
                return False

        return True  # Didn't exist, which is fine

    def sync_links(
        self,
        enabled_skills: Set[str],
        strategy: str = "symlink",
    ) -> Dict[str, List[str]]:
        """
        Synchronize all links to match the enabled skills set.

        Args:
            enabled_skills: Set of skill names that should be linked
            strategy: Link strategy ('symlink' or 'copy')

        Returns:
            Dict with 'created', 'updated', 'removed', 'failed' lists
        """
        if not self.index._loaded:
            self.index.load()

        # Ensure target directory exists
        self.link_target.mkdir(parents=True, exist_ok=True)

        result = {
            "created": [],
            "updated": [],
            "removed": [],
            "failed": [],
        }

        # Get current links
        current_links = self._list_current_links()

        # Create/update enabled skills
        for skill_name in enabled_skills:
            source_path = self._get_skill_source_path(skill_name)
            if not source_path:
                result["failed"].append(skill_name)
                continue

            link_path = self._get_link_path(skill_name)

            if link_path.is_symlink() or link_path.exists():
                # Check if needs update
                current_target = None
                if link_path.is_symlink():
                    try:
                        current_target = Path(os.readlink(link_path))
                    except OSError:
                        pass

                if current_target and current_target == source_path:
                    continue  # Already correct

                # Remove and recreate
                link_path.unlink()
                result["updated"].append(skill_name)
            else:
                result["created"].append(skill_name)

            # Create the link
            link_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                if strategy == "symlink":
                    relative_source = os.path.relpath(source_path, link_path.parent)
                    os.symlink(relative_source, link_path)
                else:
                    # Copy strategy
                    import shutil
                    shutil.copy2(source_path, link_path)
            except OSError as e:
                result["failed"].append(skill_name)

        # Remove skills that are no longer enabled
        for skill_name in current_links:
            if skill_name not in enabled_skills:
                if self.unlink_skill(skill_name):
                    result["removed"].append(skill_name)

        return result

    def _list_current_links(self) -> Set[str]:
        """
        List all currently linked skills.

        Returns:
            Set of skill names that have links
        """
        if not self.link_target.exists():
            return set()

        links = set()
        for item in self.link_target.iterdir():
            if item.is_dir():
                skill_md = item / "skill.md"
                if skill_md.is_symlink() or skill_md.exists():
                    links.add(item.name)

        return links

    def check_broken_links(self) -> List[str]:
        """
        Check for broken symlinks.

        Returns:
            List of skill names with broken links
        """
        broken = []
        current_links = self._list_current_links()

        for skill_name in current_links:
            link_path = self._get_link_path(skill_name)
            if link_path.is_symlink():
                # Resolve the symlink relative to its parent directory
                target = (link_path.parent / os.readlink(link_path)).resolve()
                if not target.exists():
                    broken.append(skill_name)

        return broken

    def get_linked_skills(self) -> List[str]:
        """
        Get list of currently linked skill names.

        Returns:
            List of skill names
        """
        return sorted(self._list_current_links())

    def clear_all_links(self) -> int:
        """
        Remove all symlinks from the target directory.

        Returns:
            Number of links removed
        """
        removed = 0
        current_links = self._list_current_links()

        for skill_name in current_links:
            if self.unlink_skill(skill_name):
                removed += 1

        return removed


def get_default_linker() -> Linker:
    """
    Get the default linker instance.

    Returns:
        A Linker instance with default paths.
    """
    return Linker()
