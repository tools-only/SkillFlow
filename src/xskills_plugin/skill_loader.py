"""
Skill Loader for X-Skills Plugin

Loads skill content from disk and processes YAML front matter.
Generates Claude Code compatible skill format.
"""

import os
import re
from pathlib import Path
from typing import Dict, Optional

from .skill_indexer import SkillIndex, SkillMetadata


class SkillLoader:
    """
    Loads skill content from the X-Skills repository.

    Handles reading skill.md files, extracting metadata, and validating
    the skill format for Claude Code compatibility.
    """

    def __init__(self, xskills_path: Optional[Path] = None):
        """
        Initialize the skill loader.

        Args:
            xskills_path: Path to the X-Skills repository.
        """
        if xskills_path is None:
            project_root = Path(__file__).parent.parent.parent
            xskills_path = project_root / "skillflow_repos" / "X-Skills"

        self.xskills_path = Path(xskills_path)
        self.index = SkillIndex(xskills_path)

    def _extract_front_matter(self, content: str) -> tuple[Dict[str, str], str]:
        """
        Extract YAML front matter from skill content.

        Args:
            content: Raw skill file content

        Returns:
            Tuple of (metadata dict, content without front matter)
        """
        metadata = {}
        body = content

        front_matter_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        if front_matter_match:
            yaml_content = front_matter_match.group(1)
            body = content[front_matter_match.end():]

            for line in yaml_content.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    metadata[key] = val

        return metadata, body

    def load_skill(self, name: str) -> Optional[str]:
        """
        Load a single skill's content by name.

        Args:
            name: The skill name (from index)

        Returns:
            The skill content as a string, or None if not found.
        """
        metadata = self.index.get_skill(name)
        if not metadata:
            return None

        skill_path = self.xskills_path / metadata.local_path / "skill.md"
        if not skill_path.exists():
            return None

        try:
            content = skill_path.read_text(encoding="utf-8")
            return content
        except Exception:
            return None

    def load_skill_with_metadata(self, name: str) -> Optional[Dict[str, str]]:
        """
        Load a skill with its metadata separated.

        Args:
            name: The skill name (from index)

        Returns:
            Dict with 'metadata' (dict) and 'content' (str), or None if not found.
        """
        raw_content = self.load_skill(name)
        if not raw_content:
            return None

        front_matter, body = self._extract_front_matter(raw_content)

        skill_metadata = self.index.get_skill(name)
        if skill_metadata:
            # Merge index metadata with front matter
            front_matter.setdefault("name", skill_metadata.name)
            front_matter.setdefault("display_name", skill_metadata.display_name)
            if not front_matter.get("description") and skill_metadata.description:
                front_matter["description"] = skill_metadata.description
            if skill_metadata.tags:
                front_matter.setdefault("tags", ", ".join(skill_metadata.tags))
            if skill_metadata.category:
                front_matter.setdefault("category", skill_metadata.category)

        return {
            "metadata": front_matter,
            "content": body,
            "raw": raw_content,
        }

    def load_skills(self, names: list[str]) -> Dict[str, str]:
        """
        Load multiple skills by name.

        Args:
            names: List of skill names

        Returns:
            Dict mapping skill name to content (missing skills are omitted)
        """
        result = {}
        for name in names:
            content = self.load_skill(name)
            if content:
                result[name] = content
        return result

    def validate_skill(self, content: str) -> tuple[bool, list[str]]:
        """
        Validate skill content for Claude Code compatibility.

        Checks for:
        - Valid YAML front matter
        - Required fields (name, description)
        - Proper markdown formatting

        Args:
            content: The skill content to validate

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check for front matter
        if not content.startswith("---"):
            errors.append("Missing YAML front matter (should start with '---')")
        else:
            front_matter, _ = self._extract_front_matter(content)

            # Check for required fields
            if not front_matter.get("name") and not front_matter.get("display_name"):
                errors.append("Missing 'name' or 'display_name' in front matter")

            if not front_matter.get("description"):
                errors.append("Missing 'description' in front matter")

        # Check for basic markdown structure
        if not any(line.strip().startswith("#") for line in content.split("\n")[:20]):
            errors.append("No heading found in first 20 lines")

        return len(errors) == 0, errors

    def get_skill_path(self, name: str) -> Optional[Path]:
        """
        Get the filesystem path for a skill.

        Args:
            name: The skill name

        Returns:
            Path to the skill.md file, or None if not found
        """
        metadata = self.index.get_skill(name)
        if not metadata:
            return None

        return self.xskills_path / metadata.local_path / "skill.md"

    def list_available_skills(self) -> list[str]:
        """
        List all available skill names.

        Returns:
            List of skill names
        """
        if not self.index._loaded:
            self.index.load()
        return list(self.index.skills.keys())

    def search_skills(self, query: str) -> list[SkillMetadata]:
        """
        Search for skills by query string.

        Args:
            query: Search query

        Returns:
            List of matching skill metadata
        """
        return self.index.list_skills(search_query=query)


def get_default_loader() -> SkillLoader:
    """
    Get the default skill loader instance.

    Returns:
        A SkillLoader instance pointing to the default X-Skills path.
    """
    return SkillLoader()
