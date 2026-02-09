"""Skill Browser - Browse and search X-Skills repository.

Provides functionality to browse, search, and get information about
skills from the X-Skills repository.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from difflib import SequenceMatcher

from src.config import Config


logger = logging.getLogger(__name__)


class SkillBrowser:
    """Browse and search skills from X-Skills repository.

    Provides methods for:
    - Listing skills by category
    - Searching skills by keyword
    - Getting skill information and content
    - Computing similarity scores for search results
    """

    def __init__(self, config: Optional[Config] = None):
        """Initialize the Skill Browser.

        Args:
            config: Optional configuration object
        """
        self.config = config or Config()
        self.xskills_dir = Path(self.config.get(
            "xskills.directory",
            "skillflow_repos/X-Skills"
        ))

        # Load skill index
        self._skill_index: Dict[str, Any] = {}
        self._load_skill_index()

    def _load_skill_index(self) -> None:
        """Load skill index from X-Skills repository.

        The .index.json file contains metadata about all skills.
        """
        index_file = self.xskills_dir / ".index.json"

        if not index_file.exists():
            logger.warning(f"Skill index not found: {index_file}")
            return

        try:
            with open(index_file, "r") as f:
                data = json.load(f)

            for skill_data in data.get("skills", []):
                self._skill_index[skill_data["file_hash"]] = skill_data

            logger.debug(f"Loaded {len(self._skill_index)} skills from index")

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading skill index: {e}")

    def list_skills(
        self,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List skills from the repository.

        Args:
            category: Filter by category (e.g., "research", "development")
            limit: Maximum number of results

        Returns:
            List of skill information dictionaries
        """
        skills = []

        for skill_data in self._skill_index.values():
            # Filter by category
            if category and skill_data.get("category") != category:
                continue

            skills.append({
                "path": f"{skill_data['category']}/{skill_data['name']}",
                "name": skill_data.get("display_name", skill_data["name"]),
                "category": skill_data.get("category", "N/A"),
                "description": skill_data.get("description", ""),
                "tags": self._parse_tags(skill_data.get("tags")),
                "source": skill_data.get("source_repo", "N/A"),
            })

        return skills[:limit]

    def search_skills(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search skills by keyword.

        Args:
            query: Search query string
            category: Filter by category
            limit: Maximum number of results

        Returns:
            List of matching skills with relevance scores
        """
        query_lower = query.lower()

        results = []

        for skill_data in self._skill_index.values():
            # Filter by category
            if category and skill_data.get("category") != category:
                continue

            # Get searchable text
            name = skill_data.get("display_name", skill_data["name"]).lower()
            tags = self._parse_tags(skill_data.get("tags"))
            source = skill_data.get("source_repo", "").lower()

            # Calculate relevance score
            score = 0

            # Exact match in name
            if query_lower in name:
                score += 100

            # Partial match in name
            score += SequenceMatcher(None, query_lower, name).ratio() * 50

            # Match in tags
            for tag in tags:
                if query_lower in tag.lower():
                    score += 30

            # Match in source
            if query_lower in source:
                score += 10

            if score > 0:
                results.append({
                    "path": f"{skill_data['category']}/{skill_data['name']}",
                    "name": skill_data.get("display_name", skill_data["name"]),
                    "category": skill_data.get("category", "N/A"),
                    "description": skill_data.get("description", ""),
                    "tags": tags,
                    "source": skill_data.get("source_repo", "N/A"),
                    "score": int(score),
                })

        # Sort by score and return top results
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def get_skill_info(self, skill_path: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a skill.

        Args:
            skill_path: Skill path (e.g., "research/094-searching_f25e7adf")

        Returns:
            Skill information dictionary or None if not found
        """
        # Parse path
        parts = skill_path.split("/", 1)
        if len(parts) != 2:
            return None

        category, skill_name = parts

        # Find skill in index
        for skill_data in self._skill_index.values():
            if (skill_data.get("category") == category and
                skill_data.get("name") == skill_name):

                # Load description from skill README
                skill_dir = self.xskills_dir / category / skill_name
                description = "No description available"

                if skill_dir.exists():
                    readme_file = skill_dir / "README.md"
                    if readme_file.exists():
                        content = readme_file.read_text()
                        # Extract description
                        for line in content.split("\n"):
                            if "## Description" in line:
                                break
                            if line.strip() and not line.startswith("#"):
                                description = line.strip()
                                break

                return {
                    "path": skill_path,
                    "display_name": skill_data.get("display_name", skill_name),
                    "category": skill_data.get("category", "N/A"),
                    "source": skill_data.get("source_repo", "N/A"),
                    "source_url": skill_data.get("source_url", ""),
                    "tags": self._parse_tags(skill_data.get("tags")),
                    "description": description,
                    "created_at": skill_data.get("indexed_at", ""),
                }

        return None

    def get_skill_content(self, skill_path: str) -> Optional[str]:
        """Get the full content of a skill.

        Args:
            skill_path: Skill path (e.g., "research/094-searching_f25e7adf")

        Returns:
            Skill content as string or None if not found
        """
        # Parse path
        parts = skill_path.split("/", 1)
        if len(parts) != 2:
            return None

        category, skill_name = parts

        # Read skill file
        skill_file = self.xskills_dir / category / skill_name / "skill.md"

        if not skill_file.exists():
            return None

        return skill_file.read_text()

    def get_installed_skills(self) -> List[Dict[str, Any]]:
        """Get list of installed skills from Claude Code.

        Returns:
            List of installed skill information
        """
        claude_skills_dir = Path.home() / ".claude" / "skills"
        if not claude_skills_dir.exists():
            return []

        skills = []

        # Scan for patch directories
        for patch_dir in claude_skills_dir.iterdir():
            if not patch_dir.is_dir() or not patch_dir.name.startswith("patch-"):
                continue

            patch_id = patch_dir.name.replace("patch-", "")

            # List skills in patch
            for skill_dir in patch_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                skills.append({
                    "path": f"{patch_id}/{skill_dir.name}",
                    "name": skill_dir.name,
                    "category": "installed",
                    "tags": [],
                    "source": patch_id,
                })

        return skills

    def list_categories(self) -> List[str]:
        """List all available skill categories.

        Returns:
            List of category names
        """
        categories = set()

        for skill_data in self._skill_index.values():
            categories.add(skill_data.get("category", "other"))

        return sorted(categories)

    def get_category_stats(self) -> Dict[str, int]:
        """Get skill count per category.

        Returns:
            Dictionary mapping category to skill count
        """
        stats = {}

        for skill_data in self._skill_index.values():
            category = skill_data.get("category", "other")
            stats[category] = stats.get(category, 0) + 1

        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))

    def _parse_tags(self, tags: Any) -> List[str]:
        """Parse tags from various formats.

        Args:
            tags: Tags in various formats (string, list, dict)

        Returns:
            List of tag strings
        """
        if not tags:
            return []

        if isinstance(tags, list):
            return tags

        if isinstance(tags, str):
            try:
                parsed = json.loads(tags)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []

        return []


__all__ = ["SkillBrowser"]
