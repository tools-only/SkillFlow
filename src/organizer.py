"""Skill organization module for category-based file organization."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import Config
from .skill_analyzer import SkillMetadata


logger = logging.getLogger(__name__)


class SkillOrganizer:
    """Organize skill files into category-based folder structure."""

    def __init__(self, config: Config):
        """Initialize skill organizer.

        Args:
            config: Configuration object
        """
        self.config = config
        self.skills_dir = config.skills_dir

    def organize_skill(
        self,
        metadata: SkillMetadata,
        content: str,
        source_info: dict,
    ) -> Optional[Path]:
        """Organize a skill file into the appropriate category structure.

        Args:
            metadata: Skill metadata from analysis
            content: Original skill content
            source_info: Source information dict with keys:
                - source_repo: Repository full name
                - source_path: Path in original repository
                - source_url: URL to original file
                - file_hash: Hash of content

        Returns:
            Path to the organized skill file, or None if error
        """
        try:
            # Create category structure
            category_path = self.ensure_category_structure(metadata.category, metadata.subcategory)

            # Sanitize filename from skill name
            filename = self._sanitize_filename(metadata.name)
            if not filename.endswith(".md"):
                filename += ".md"

            skill_path = category_path / filename

            # If file already exists, add numeric suffix
            counter = 1
            base_path = skill_path
            while skill_path.exists():
                stem = base_path.stem
                skill_path = category_path / f"{stem}_{counter}.md"
                counter += 1

            # Build the file content with header
            file_content = self._build_file_content(metadata, content, source_info)

            # Write the file
            with open(skill_path, "w", encoding="utf-8") as f:
                f.write(file_content)

            logger.info(f"Organized skill: {skill_path}")
            return skill_path

        except IOError as e:
            logger.error(f"Error writing skill file: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error organizing skill: {e}")
            return None

    def ensure_category_structure(self, category: str, subcategory: str) -> Path:
        """Ensure the category/subcategory directory structure exists.

        Args:
            category: Main category name
            subcategory: Subcategory name

        Returns:
            Path to the subcategory directory
        """
        # Normalize category and subcategory names
        category = self._sanitize_category_name(category)
        subcategory = self._sanitize_category_name(subcategory)

        # Create directory structure
        category_path = self.skills_dir / category
        subcategory_path = category_path / subcategory

        # Create directories if they don't exist
        subcategory_path.mkdir(parents=True, exist_ok=True)

        return subcategory_path

    def _sanitize_category_name(self, name: str) -> str:
        """Sanitize category/subcategory name for use in file paths.

        Args:
            name: Category name to sanitize

        Returns:
            Sanitized name
        """
        # Convert to lowercase, replace spaces with hyphens
        name = name.lower().strip()
        name = name.replace(" ", "-").replace("_", "-")
        # Remove any characters that aren't alphanumeric, hyphen, or dot
        name = "".join(c for c in name if c.isalnum() or c in "-.")
        return name or "general"

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize skill name for use as filename.

        Args:
            name: Skill name to sanitize

        Returns:
            Sanitized filename
        """
        # Remove or replace problematic characters
        name = name.strip()
        name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        name = name.replace(":", "_").replace("*", "_").replace("?", "_")
        name = name.replace('"', "_").replace("<", "_").replace(">", "_")
        name = name.replace("|", "_")
        # Limit length
        if len(name) > 100:
            name = name[:97] + "..."
        return name or "unnamed_skill"

    def _build_file_content(
        self,
        metadata: SkillMetadata,
        original_content: str,
        source_info: dict,
    ) -> str:
        """Build the complete file content with YAML header.

        Args:
            metadata: Skill metadata
            original_content: Original skill markdown content
            source_info: Source information dict

        Returns:
            Complete file content with header
        """
        # Get current timestamp
        updated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        # Format tags as YAML list
        tags_str = str(metadata.tags).replace("'", "")

        # Build YAML header
        header = f"""---
name: {metadata.name}
description: {metadata.description}
source: {source_info.get('source_url', 'unknown')}
original_path: {source_info.get('source_path', 'unknown')}
source_repo: {source_info.get('source_repo', 'unknown')}
updated_at: {updated_at}
category: {metadata.category}
subcategory: {metadata.subcategory}
tags: {tags_str}
primary_purpose: {metadata.primary_purpose}
file_hash: {source_info.get('file_hash', '')}
---

"""

        return header + original_content

    def get_category_stats(self) -> dict[str, dict[str, int]]:
        """Get statistics about skills in each category.

        Returns:
            Dict mapping category -> {subcategory: count}
        """
        stats: dict[str, dict[str, int]] = {}

        if not self.skills_dir.exists():
            return stats

        for category_dir in self.skills_dir.iterdir():
            if category_dir.is_dir():
                category = category_dir.name
                stats[category] = {}

                for subcategory_dir in category_dir.iterdir():
                    if subcategory_dir.is_dir():
                        subcategory = subcategory_dir.name
                        # Count markdown files
                        md_count = sum(1 for f in subcategory_dir.iterdir() if f.is_file() and f.suffix == ".md")
                        stats[category][subcategory] = md_count

        return stats

    def find_existing_skill(self, file_hash: str) -> Optional[Path]:
        """Find if a skill with the given hash already exists.

        Args:
            file_hash: Hash of the skill content

        Returns:
            Path to existing skill file, or None if not found
        """
        if not self.skills_dir.exists():
            return None

        # Search through all markdown files
        for md_file in self.skills_dir.rglob("*.md"):
            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    # Read the YAML header
                    lines = []
                    for line in f:
                        lines.append(line)
                        if line.strip() == "---":
                            break

                    # Check if file_hash is in the header
                    content = "".join(lines)
                    if f'file_hash: {file_hash}' in content:
                        return md_file
            except (IOError, UnicodeDecodeError):
                continue

        return None
