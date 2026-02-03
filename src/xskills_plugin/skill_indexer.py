"""
Skill Indexer for X-Skills Plugin

Parses .index.json and scans skill directories to build an in-memory index
of all available skills with their metadata.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class SkillMetadata:
    """Metadata for a single skill."""

    name: str
    display_name: str
    description: str
    category: str
    subcategory: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    local_path: str = ""
    file_hash: str = ""
    source_repo: Optional[str] = None
    source_url: Optional[str] = None
    repo_stars: Optional[int] = None
    repo_updated_at: Optional[str] = None
    allowed_tools: Optional[List[str]] = None
    model: Optional[str] = None

    @classmethod
    def from_index_entry(cls, entry: Dict[str, Any], xskills_base: Path) -> "SkillMetadata":
        """Create SkillMetadata from an index.json entry."""
        tags = []
        if entry.get("tags"):
            try:
                tags_val = entry["tags"]
                if isinstance(tags_val, str):
                    # Handle string representation like '["tag1", "tag2"]'
                    tags = json.loads(tags_val.replace("'", '"'))
                elif isinstance(tags_val, list):
                    tags = tags_val
            except (json.JSONDecodeError, TypeError):
                tags = []

        local_path = entry.get("local_path", "")

        # Try to read actual skill.md for better metadata
        skill_full_path = xskills_base / local_path / "skill.md"
        display_name = entry.get("display_name", "Skill")
        description = ""

        if skill_full_path.exists():
            try:
                content = skill_full_path.read_text(encoding="utf-8")
                # Extract YAML front matter
                yaml_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
                if yaml_match:
                    yaml_content = yaml_match.group(1)
                    for line in yaml_content.split("\n"):
                        if ":" in line:
                            key, val = line.split(":", 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if key == "display_name" or key == "name":
                                display_name = val
                            elif key == "description":
                                description = val
                # Use first heading or paragraph as description if not set
                if not description:
                    # Find first heading or paragraph
                    lines = content.split("\n")
                    for line in lines:
                        line = line.strip()
                        if line.startswith("# "):
                            description = line.lstrip("# ").strip()
                            break
                        elif line and not line.startswith("#"):
                            description = line[:100]
                            break
            except Exception:
                pass

        return cls(
            name=entry.get("name", local_path.replace("/", "-")),
            display_name=display_name,
            description=description or entry.get("display_name", "Skill"),
            category=entry.get("category", "other"),
            subcategory=entry.get("subcategory"),
            tags=tags,
            local_path=local_path,
            file_hash=entry.get("file_hash", ""),
            source_repo=entry.get("source_repo"),
            source_url=entry.get("source_url"),
            repo_stars=entry.get("repo_stars"),
            repo_updated_at=entry.get("repo_updated_at"),
        )


class SkillIndex:
    """
    Index of all available skills from X-Skills repository.

    Provides methods for searching and filtering skills by category, tags, etc.
    """

    def __init__(self, xskills_path: Optional[Path] = None):
        """
        Initialize the skill index.

        Args:
            xskills_path: Path to the X-Skills repository.
                         If None, uses default ./skillflow_repos/X-Skills
        """
        if xskills_path is None:
            # Default path relative to project root
            project_root = Path(__file__).parent.parent.parent
            xskills_path = project_root / "skillflow_repos" / "X-Skills"

        self.xskills_path = Path(xskills_path)
        self.skills: Dict[str, SkillMetadata] = {}
        self.by_category: Dict[str, List[str]] = {}
        self.by_tags: Dict[str, List[str]] = {}
        self._loaded = False

    def load(self, force_reload: bool = False) -> None:
        """
        Load skill index from .index.json and scan skill directories.

        Args:
            force_reload: Force reload even if already loaded.
        """
        if self._loaded and not force_reload:
            return

        self.skills.clear()
        self.by_category.clear()
        self.by_tags.clear()

        index_path = self.xskills_path / ".index.json"

        if not index_path.exists():
            raise FileNotFoundError(f"Index file not found: {index_path}")

        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)

        for entry in index_data.get("skills", []):
            try:
                metadata = SkillMetadata.from_index_entry(entry, self.xskills_path)
                self.skills[metadata.name] = metadata

                # Index by category
                if metadata.category not in self.by_category:
                    self.by_category[metadata.category] = []
                self.by_category[metadata.category].append(metadata.name)

                # Index by tags
                for tag in metadata.tags:
                    if tag not in self.by_tags:
                        self.by_tags[tag] = []
                    self.by_tags[tag].append(metadata.name)

            except Exception as e:
                # Skip invalid entries but continue loading
                continue

        self._loaded = True

    def get_skill(self, name: str) -> Optional[SkillMetadata]:
        """Get metadata for a specific skill by name."""
        if not self._loaded:
            self.load()
        return self.skills.get(name)

    def list_skills(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search_query: Optional[str] = None,
    ) -> List[SkillMetadata]:
        """
        List skills with optional filtering.

        Args:
            category: Filter by category (e.g., 'development', 'automation')
            tags: Filter by tags (must match all specified tags)
            search_query: Search in display name and description

        Returns:
            List of matching skill metadata.
        """
        if not self._loaded:
            self.load()

        results = list(self.skills.values())

        if category:
            results = [s for s in results if s.category == category]

        if tags:
            results = [
                s
                for s in results
                if all(tag in s.tags for tag in tags)
            ]

        if search_query:
            query_lower = search_query.lower()
            results = [
                s
                for s in results
                if query_lower in s.display_name.lower()
                or query_lower in s.description.lower()
                or query_lower in s.name.lower()
            ]

        return sorted(results, key=lambda s: s.display_name.lower())

    def list_categories(self) -> List[str]:
        """Get list of all available categories."""
        if not self._loaded:
            self.load()
        return sorted(self.by_category.keys())

    def list_tags(self) -> List[str]:
        """Get list of all available tags."""
        if not self._loaded:
            self.load()
        return sorted(self.by_tags.keys())

    def get_skills_by_category(self, category: str) -> List[SkillMetadata]:
        """Get all skills in a specific category."""
        if not self._loaded:
            self.load()
        names = self.by_category.get(category, [])
        return [self.skills[name] for name in names if name in self.skills]

    def count(self) -> int:
        """Get total number of indexed skills."""
        if not self._loaded:
            self.load()
        return len(self.skills)

    def refresh(self) -> None:
        """Refresh the index by reloading from disk."""
        self.load(force_reload=True)


def get_default_index() -> SkillIndex:
    """
    Get the default skill index instance.

    Returns:
        A SkillIndex instance pointing to the default X-Skills path.
    """
    return SkillIndex()
